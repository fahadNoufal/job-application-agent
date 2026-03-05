"""
src/platforms/naukri/applier.py

Handles all three Naukri application flows:

  CASE 1A — Apply button → immediate success message
  CASE 1B — Apply button → chatbot Q&A appears
  CASE 2  — "I am interested" (walkin) button → chatbot Q&A
  CASE 3  — Apply button redirects to external company website
             → link saved to external_links table in DB, skip automation

LLM answers chatbot questions in conversational mode:
each question is answered individually, with full Q&A history
passed as context so answers stay consistent throughout.
"""

import asyncio
from playwright.async_api import Page

from src.platforms.naukri import selectors as S
from src.platforms.naukri.schemas import ChatMessage
from src.platforms.naukri.scraper import fetch_job_description
from src.llm.generator import answer_chatbot_question
from src.storage.database import insert_external_link
from src.browser.actions import navigate, safe_click, human_delay
from src.utils.logger import get_logger

logger = get_logger("naukri.applier")


# ── Entry point ────────────────────────────────────────────────────────────────

async def apply_to_job(
    page: Page,
    job: dict,
    resume_summary: str,
    preferences_md: str,
    automation_mode: str = "semi_automated",
) -> dict:
    """
    Full application flow for a single Naukri job.
    Returns a result dict with status and any error.
    """
    result = {
        "link": job["link"],
        "title": job["title"],
        "company": job["company"],
        "status": "failed",
        "error": None,
        "raw_questions": [],
    }

    try:
        description = job.get("description") or await fetch_job_description(page, job["link"])

        logger.info(f"Navigating to: {job['link']}")
        await page.goto(job["link"], wait_until="domcontentloaded", timeout=60_000)

        # Wait for any one of the known buttons / status indicators
        try:
            await page.wait_for_selector(
                f"{S.APPLY_BTN}, {S.COMPANY_SITE_BTN}, {S.WALKIN_BTN}, {S.ALREADY_APPLIED}",
                timeout=15_000,
            )
        except Exception:
            logger.warning("Timed out waiting for apply buttons — proceeding anyway.")

        # ── Already applied? ───────────────────────────────────────────────────
        if await page.locator(S.ALREADY_APPLIED).count() > 0:
            result["status"] = "already_applied"
            logger.info(f"Already applied: {job['title']} @ {job['company']}")
            return result

        apply_btn  = page.locator(S.APPLY_BTN).first
        walkin_btn = page.locator(S.WALKIN_BTN).first
        company_site_btn = page.locator(S.COMPANY_SITE_BTN).first
        has_apply  = await apply_btn.count() > 0
        has_walkin = await walkin_btn.count() > 0
        has_company_site = await company_site_btn.count() > 0
        

        # Build LLM context once — shared across all chatbot turns
        llm_context = {
            "job_title": job["title"],
            "company": job["company"],
            "description": description,
            "resume_summary": resume_summary,
            "preferences_md": preferences_md,
        }

        if has_apply:
            outcome = await _handle_apply_button(
                page, apply_btn, job, llm_context, result, automation_mode
            )
        elif has_walkin:
            logger.info(f"[CASE 2] 'I am interested' button — {job['title']}")
            await safe_click(walkin_btn)
            await page.wait_for_selector(S.CHAT_LIST, timeout=10_000)

            if automation_mode == "semi_automated":
                if not await _confirm_submission(job):
                    result["status"] = "skipped"
                    return result

            chat_history = await _chatbot_loop(page, llm_context)
            result["raw_questions"] = [m.model_dump() for m in chat_history]
            outcome = "applied"
        elif has_company_site:
            logger.info(f"[CASE 3] 'Apply on company site' button — {job['title']}")
            outcome = await _handle_external(page, company_site_btn, job)
        else:
            result["error"] = "No apply or walkin button found."
            logger.error(f"No apply button: {job['link']}")
            return result

        result["status"] = outcome
        if outcome == "applied":
            logger.info(f"✓ Applied: {job['title']} @ {job['company']}")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"✗ Exception applying to {job['link']}: {e}")

    return result


# ── Apply button handler ───────────────────────────────────────────────────────

async def _handle_apply_button(
    page: Page,
    apply_btn,
    job: dict,
    llm_context: dict,
    result: dict,
    automation_mode: str,
) -> str:
    """
    Click Apply and handle whichever outcome follows:
      - Immediate success  → return "applied"
      - Chatbot appears    → run chatbot loop → return "applied"
      - External redirect  → save link to DB → return "external"
    """
    original_url = page.url

    # Pre-click check: does the button text say "apply on company website"?
    btn_text = (await apply_btn.text_content() or "").strip().lower()
    if "company website" in btn_text or "external" in btn_text:
        return await _handle_external(page, apply_btn, job)

    # Confirm before clicking in semi-automated mode
    if automation_mode == "semi_automated":
        if not await _confirm_submission(job):
            return "skipped"

    logger.info(f"[CASE 1] Clicking Apply: {job['title']}")
    await safe_click(apply_btn)
    await human_delay(2.0, 3.0)

    # Redirected to external site after click?
    if "naukri.com" not in page.url and page.url != original_url:
        return await _save_external_redirect(page.url, job)

    # Wait for success message OR chatbot
    try:
        await page.wait_for_selector(
            f"{S.APPLY_SUCCESS}, {S.CHAT_LIST}",
            timeout=15_000,
        )
    except Exception:
        if "naukri.com" not in page.url:
            return await _save_external_redirect(page.url, job)
        logger.warning("Nothing detected 15s after Apply click.")
        return "failed"

    # ── Case 1A: Immediate success ─────────────────────────────────────────────
    if await page.locator(S.APPLY_SUCCESS).count() > 0:
        msg = (await page.locator(S.APPLY_SUCCESS).first.text_content() or "").strip()
        logger.info(f"  Instant success: {msg}")
        return "applied"

    # ── Case 1B: Chatbot appeared ──────────────────────────────────────────────
    if await page.locator(S.CHAT_LIST).count() > 0:
        logger.info("  [CASE 1B] Chatbot appeared after Apply.")
        chat_history = await _chatbot_loop(page, llm_context)
        result["raw_questions"] = [m.model_dump() for m in chat_history]
        return "applied"

    return "failed"


# ── External redirect helpers ──────────────────────────────────────────────────

async def _handle_external(page: Page, apply_btn, job: dict) -> str:
    """Button text signals external site — open in new tab to capture URL."""
    try:
        async with page.context.expect_page() as new_page_info:
            await apply_btn.click()
        new_page = await new_page_info.value
        await new_page.wait_for_load_state("domcontentloaded")
        external_url = new_page.url
    except Exception:
        external_url = job["link"]   # fallback to job link itself

    return await _save_external_redirect(external_url, job)


async def _save_external_redirect(external_url: str, job: dict) -> str:
    """Persist the external link to the DB and return status 'external'."""
    logger.info(f"  🔗 External redirect: {external_url}")
    await insert_external_link(
        platform="naukri",
        job_title=job["title"],
        company=job["company"],
        original_link=job["link"],
        external_link=external_url,
    )
    return "external"


# ── Chatbot loop ───────────────────────────────────────────────────────────────

async def _chatbot_loop(page: Page, llm_context: dict) -> list[ChatMessage]:
    """
    Sequential chatbot Q&A loop.
    Each question is answered by the LLM in conversational mode:
    the full history of prior Q&As is passed with every call so the
    LLM can keep answers consistent (e.g. experience, availability).

    Returns the full conversation history as a list of ChatMessage objects.
    """
    history: list[ChatMessage] = []
    seen_bot_messages: set[str] = set()
    idle = 0
    max_idle = 10

    while True:
        await asyncio.sleep(2)

        # ── Check for success ──────────────────────────────────────────────────
        if await page.locator(S.APPLY_SUCCESS).count() > 0:
            msg = (await page.locator(S.APPLY_SUCCESS).first.text_content() or "").strip()
            logger.info(f"  ✓ Chatbot done: {msg}")
            break

        # ── Radio question ─────────────────────────────────────────────────────
        radio_container = page.locator(S.RADIO_CONTAINER).first
        if await radio_container.count() > 0:
            question_text = await _get_latest_bot_message(page, seen_bot_messages)
            if question_text:
                seen_bot_messages.add(question_text)
                options = await _get_radio_options(radio_container)

                answer = await answer_chatbot_question(
                    question=question_text,
                    options=options,
                    history=history,
                    **llm_context,
                )
                logger.info(f"  Q: {question_text[:60]}  →  A: {answer}")

                history.append(ChatMessage(
                    role="user",
                    question=question_text,
                    options=options,
                    answer=answer,
                ))

                await _click_radio_option(radio_container, answer)
                await _click_save(page)
                idle = 0
                continue

        # ── Text input question ────────────────────────────────────────────────
        input_el = page.locator(S.TEXT_INPUT).first
        if await input_el.count() > 0:
            question_text = await _get_latest_bot_message(page, seen_bot_messages)
            if not question_text:
                await asyncio.sleep(1)
                continue
            seen_bot_messages.add(question_text)

            answer = await answer_chatbot_question(
                question=question_text,
                options=[],
                history=history,
                **llm_context,
            )
            logger.info(f"  Q: {question_text[:60]}  →  A: {answer}")

            history.append(ChatMessage(
                role="user",
                question=question_text,
                options=[],
                answer=answer,
            ))

            await _type_in_input(page, input_el, answer)
            await _click_save(page)
            idle = 0
            continue

        # ── Idle guard ─────────────────────────────────────────────────────────
        idle += 1
        if idle >= max_idle:
            logger.warning("Chatbot idle limit reached. Exiting loop.")
            break
        logger.debug(f"Waiting for next chatbot question... ({idle}/{max_idle})")

    return history


# ── Chatbot DOM helpers ────────────────────────────────────────────────────────

async def _get_latest_bot_message(page: Page, seen: set[str]) -> str | None:
    """Return the most recent bot message not yet seen."""
    spans = page.locator(S.BOT_MESSAGES)
    count = await spans.count()
    for i in range(count - 1, -1, -1):
        text = (await spans.nth(i).text_content() or "").strip()
        if text and text not in seen:
            return text
    return None


async def _get_radio_options(container) -> list[str]:
    inputs = container.locator(S.RADIO_INPUTS)
    count = await inputs.count()
    options = []
    for i in range(count):
        val = await inputs.nth(i).get_attribute("value") or ""
        if val:
            options.append(val)
    return options


async def _click_radio_option(container, answer: str) -> None:
    """Click the radio matching answer text. Tries label click then JS click."""
    inputs = container.locator(S.RADIO_INPUTS)
    count = await inputs.count()

    for i in range(count):
        radio = inputs.nth(i)
        val = (await radio.get_attribute("value") or "").strip().lower()
        if val == answer.strip().lower():
            radio_id = await radio.get_attribute("id") or ""
            # Prefer label click — always visible even if radio is off-screen
            if radio_id:
                label = container.locator(f"label[for='{radio_id}']").first
                if await label.count() > 0:
                    await label.scroll_into_view_if_needed()
                    await label.click()
                    logger.debug(f"Radio selected (label): {answer}")
                    return
            # Fallback: JS click bypasses viewport restriction
            await radio.evaluate("el => el.click()")
            logger.debug(f"Radio selected (JS): {answer}")
            return

    logger.warning(f"Radio option '{answer}' not found. Available: {await _get_radio_options(container)}")


async def _type_in_input(page: Page, input_el, answer: str) -> None:
    """Type into Naukri's contenteditable div (doesn't support .fill())."""
    await input_el.click()
    await page.keyboard.press("Control+a")
    await page.keyboard.type(answer)
    logger.debug(f"Typed into text input: {answer[:40]}")


async def _click_save(page: Page) -> None:
    save_btn = page.locator(S.SAVE_BTN).first
    await save_btn.wait_for(state="visible", timeout=5_000)
    await save_btn.click()
    logger.debug("Save/Send clicked.")
    await asyncio.sleep(2)


# ── Semi-automated confirmation ────────────────────────────────────────────────

async def _confirm_submission(job: dict) -> bool:
    print(
        f"\n{'─' * 60}\n"
        f"📋  Ready to apply: {job['title']} @ {job['company']}\n"
        f"🔗  {job['link']}\n"
        f"{'─' * 60}\n"
        f"  [ENTER]   → Proceed with application\n"
        f"  [s+ENTER] → Skip this job\n"
    )
    return input("Your choice: ").strip().lower() != "s"