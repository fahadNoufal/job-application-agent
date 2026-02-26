"""
src/platforms/internshala/applier.py
Handles navigating to a job listing and filling / submitting the application form.
Based on verified working flow: #top_easy_apply_button → #assessment_questions → #submit
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Any, Optional

from playwright.async_api import Page

from src.browser.actions import human_delay
from src.llm.generator import generate_answers
from src.utils.logger import get_logger

logger = get_logger("internshala.applier")
log = logger  # alias used in helper functions


# ── Data class for a parsed question ──────────────────────────────────────────

@dataclass
class QuestionDict:
    heading: str
    type: str           # text | radio | availability | checkbox | select | file
    question: str
    options: list[str]
    description: Optional[str]
    required: bool
    field_name: Optional[str]
    field_id: Optional[str]
    conditional: bool


# ── JavaScript extractor (runs inside the browser) ────────────────────────────

_EXTRACTOR_JS = """
() => {
  const questions = [];

  const clean = s => (s || '').replace(/\\s+/g, ' ').trim();

  function hasRequired(container) {
    if (container.querySelector("[aria-required='true']")) return true;
    const err = container.querySelector(".form-error");
    if (err) return true;
    return false;
  }

  function radioOptions(container) {
    return Array.from(container.querySelectorAll("input[type='radio']")).map(r => {
      const lbl = container.querySelector(`label[for='${r.id}']`);
      return clean(lbl ? lbl.textContent : r.value);
    });
  }

  function checkboxOptions(container) {
    return Array.from(container.querySelectorAll("input[type='checkbox']")).map(c => {
      const lbl = container.querySelector(`label[for='${c.id}']`);
      return clean(lbl ? lbl.textContent : c.value);
    });
  }

  const root = document.querySelector("#assessment_questions");
  if (!root) return questions;

  // 1. Cover Letter
  const coverGroup = root.querySelector(".form-group:has(#cover_letter_holder), .form-group:has(#cover_letter)");
  if (coverGroup) {
    const headingEl = root.querySelector("h4.question-heading");
    const labelEl   = coverGroup.querySelector(".assessment_question label");
    questions.push({
      heading:     clean(headingEl ? headingEl.textContent : "Cover Letter"),
      type:        "text",
      question:    clean(labelEl ? labelEl.textContent : "Why should you be hired for this role?"),
      options:     [],
      description: null,
      required:    hasRequired(coverGroup),
      field_name:  "cover_letter",
      field_id:    "cover_letter",
      conditional: false,
    });
  }

  // 2. Confirm Availability
  const availSection = root.querySelector("#confirm_availability_container");
  if (availSection) {
    const heading = clean(availSection.querySelector(".question-heading")?.textContent || "Confirm your availability");
    questions.push({
      heading,
      type:        "availability",
      question:    heading,
      options:     radioOptions(availSection),
      description: null,
      required:    true,
      field_name:  "confirm_availability",
      field_id:    null,
      conditional: false,
    });
  }

  // 3. Additional / Custom Questions
  const addContainer = root.querySelector(".questions-container");
  if (addContainer) {
    const sectionHeading = clean(
      addContainer.querySelector(".additional-question-heading, h4")?.textContent
      || "Additional questions"
    );

    addContainer.querySelectorAll(".additional_question, .form-group.additional_question").forEach(block => {
      const labelEl = block.querySelector(".assessment_question label");
      const question = clean(labelEl ? labelEl.textContent : "");
      if (!question) return;

      const radios = block.querySelectorAll("input[type='radio']");
      if (radios.length) {
        questions.push({
          heading: sectionHeading, type: "radio", question,
          options: radioOptions(block), description: null,
          required: hasRequired(block), field_name: radios[0].name,
          field_id: null, conditional: false,
        });
        return;
      }

      const checks = block.querySelectorAll("input[type='checkbox']");
      if (checks.length) {
        questions.push({
          heading: sectionHeading, type: "checkbox", question,
          options: checkboxOptions(block), description: null,
          required: hasRequired(block), field_name: checks[0].name,
          field_id: null, conditional: false,
        });
        return;
      }

      const sel = block.querySelector("select");
      if (sel) {
        const opts = Array.from(sel.options).filter(o => !o.disabled).map(o => clean(o.textContent));
        questions.push({
          heading: sectionHeading, type: "select", question,
          options: opts, description: null,
          required: hasRequired(block), field_name: sel.name,
          field_id: sel.id || null, conditional: false,
        });
        return;
      }

      const ta = block.querySelector("textarea:not([style*='display: none'])");
      if (ta) {
        questions.push({
          heading: sectionHeading, type: "text", question,
          options: [], description: clean(ta.getAttribute("placeholder") || ""),
          required: hasRequired(block), field_name: ta.name || null,
          field_id: ta.id || null, conditional: false,
        });
        return;
      }

      const inp = block.querySelector("input[type='text'],input[type='email'],input[type='number']");
      if (inp) {
        questions.push({
          heading: sectionHeading, type: "text", question,
          options: [], description: clean(inp.getAttribute("placeholder") || ""),
          required: hasRequired(block), field_name: inp.name || null,
          field_id: inp.id || null, conditional: false,
        });
        return;
      }

      const fileInp = block.querySelector("input[type='file']");
      if (fileInp) {
        questions.push({
          heading: sectionHeading, type: "file", question,
          options: [], description: null,
          required: hasRequired(block), field_name: fileInp.name || null,
          field_id: fileInp.id || null, conditional: false,
        });
      }
    });
  }

  return questions;
}
"""


# ── Core public functions ──────────────────────────────────────────────────────

async def extract_form_questions(page: Page) -> list[QuestionDict]:
    """
    Dynamically scrape every question inside #assessment_questions.
    Must be called AFTER the modal is open and #assessment_questions is visible.
    """
    raw: list[dict] = await page.evaluate(_EXTRACTOR_JS)
    return [QuestionDict(**q) for q in raw]


async def fill_form_answers(
    page: Page,
    questions: list[QuestionDict],
    answers: list[Any],
) -> None:
    """
    Fill the Internshala application form.

    answers must be 1-to-1 aligned with questions:
        text / textarea  → str
        radio            → str  (option label, case-insensitive)
        availability     → str  (option label, e.g. "Yes, I can join immediately")
        checkbox         → list[str] | str
        select           → str  (option label)
        file             → str  (absolute path) | None to skip
    """
    if len(answers) != len(questions):
        raise ValueError(
            f"answers length ({len(answers)}) != questions length ({len(questions)})"
        )

    for q, answer in zip(questions, answers):
        if answer is None:
            log.debug("Skipping %r (answer is None)", q.question)
            continue

        try:
            match q.type:
                case "text":
                    await _fill_text(page, q, answer)
                case "radio" | "availability":
                    await _fill_radio(page, q, answer)
                case "checkbox":
                    await _fill_checkbox(page, q, answer)
                case "select":
                    await _fill_select(page, q, answer)
                case "file":
                    log.warning("File upload not yet automated — skipping %r", q.question)
                case _:
                    log.warning("Unknown question type %r — skipped", q.type)

            await human_delay(0.3, 0.8)

        except Exception as exc:
            log.warning("Could not fill %r: %s", q.question, exc)


async def extract_job_details(page):
    # Wait for the assessment section to load (or any other stable selector)
    await page.wait_for_selector("#assessment_questions", timeout=15_000)

    # Extract Role Overview
    role_overview_items = await page.query_selector_all(".role_overview_container ul li")
    role_overview_text = " ".join([await li.inner_text() for li in role_overview_items])

    # Extract Requirements
    requirements_items = await page.query_selector_all(".requirements_container ul li")
    requirements_text = " ".join([await li.inner_text() for li in requirements_items])

    # Combine into single string
    combined_text = f"Role Overview: {role_overview_text}\nRequirements: {requirements_text}"
    return combined_text

async def apply_to_job(
    page: Page,
    job: dict,
    resume_summary: str,
    preferences_md: str,
    automation_mode: str = "semi_automated",
) -> dict:
    """
    Full application flow for a single Internshala job.
    Returns result dict with status and any error.
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
        # 1. Navigate to job page
        await page.goto(job["link"], wait_until="networkidle")

        # 2. Click the Easy Apply button
        await page.click("#top_easy_apply_button")
        await human_delay(1.5, 2.5)

        # 3. Wait for the assessment form to appear
        await page.wait_for_selector("#assessment_questions", timeout=15_000)

        # 4. Extract questions
        questions = await extract_form_questions(page)
        result["raw_questions"] = [asdict(q) for q in questions]
        log.info("Extracted %d questions for %s @ %s", len(questions), job["title"], job["company"])

        if not questions:
            log.warning("No questions found — attempting blind submit.")
        else:
            # 5. Generate answers via LLM
            brief_description = job.get("description", "")
            job_description = await extract_job_details(page) 
            description = f"Brief Overview: {brief_description}\n\n{job_description}"
            
            answers = generate_answers(
                questions=[asdict(q) for q in questions],
                resume_summary=resume_summary,
                preferences_md=preferences_md,
                job_title=job["title"],
                company=job["company"],
                description=description,
            )

            # generate_answers should return a list aligned 1-to-1 with questions
            # If it returns dicts with an "answer" key, extract just the values:
            if answers and isinstance(answers[0], dict):
                answer_values = [a.get("answer") for a in answers]
            else:
                answer_values = answers

            # 6. Fill the form
            await fill_form_answers(page, questions, answer_values)

        # Optional pause for user review in semi-automated mode
        if automation_mode == "semi_automated":
            should_submit = await _confirm_submission(job)
            if not should_submit:
                result["status"] = "skipped"
                logger.info(f"↩ Skipped by user: {job['title']} @ {job['company']}")
                return result
            
        # 7. Submit
        await _submit_form(page)
        result["status"] = "applied"
        log.info("✓ Applied: %s @ %s", job["title"], job["company"])

    except Exception as e:
        result["error"] = str(e)
        log.error("✗ Failed to apply to %s: %s", job["link"], e)

    return result


# ── Per-type fill helpers ──────────────────────────────────────────────────────

async def _fill_text(page: Page, q: QuestionDict, answer: str) -> None:
    answer = str(answer)

    # Cover letter uses a Quill rich-text editor — real <textarea> is hidden
    if q.field_id == "cover_letter":
        editor = page.locator(".ql-editor").first
        await editor.click()
        await editor.press("Control+a")
        await editor.type(answer, delay=1)
        return

    if q.field_id:
        selector = f"#{q.field_id}"
        el = page.locator(selector).first
        if await el.count() == 0 and q.field_name:
            selector = f"textarea[name='{q.field_name}'], input[name='{q.field_name}']"
            el = page.locator(selector).first
    elif q.field_name:
        selector = f"textarea[name='{q.field_name}'], input[name='{q.field_name}']"
        el = page.locator(selector).first
    else:
        raise ValueError(f"Question has no field_id or field_name: {q.question!r}")

    await el.click()
    await el.fill(answer)


async def _fill_radio(page: Page, q: QuestionDict, answer: str) -> None:
    answer_lower = answer.strip().lower()

    clicked = await page.evaluate(
        """([field_name, answer_lower]) => {
            const radios = document.querySelectorAll(`input[type='radio'][name='${field_name}']`);
            for (const r of radios) {
                const lbl = document.querySelector(`label[for='${r.id}']`);
                const text = (lbl ? lbl.textContent : r.value).toLowerCase().trim();
                if (text.includes(answer_lower) || r.value.toLowerCase() === answer_lower) {
                    r.click();
                    return true;
                }
            }
            return false;
        }""",
        [q.field_name, answer_lower],
    )

    if not clicked:
        log.warning(
            "Radio option %r not found for %r (available: %s)",
            answer, q.question, q.options,
        )


async def _fill_checkbox(page: Page, q: QuestionDict, answer: list[str] | str) -> None:
    targets = [a.strip().lower() for a in (answer if isinstance(answer, list) else [answer])]

    await page.evaluate(
        """([field_name, targets]) => {
            const boxes = document.querySelectorAll(`input[type='checkbox'][name='${field_name}']`);
            for (const cb of boxes) {
                const lbl = document.querySelector(`label[for='${cb.id}']`);
                const text = (lbl ? lbl.textContent : cb.value).toLowerCase().trim();
                const should = targets.some(t => text.includes(t) || cb.value.toLowerCase() === t);
                if (should !== cb.checked) cb.click();
            }
        }""",
        [q.field_name, targets],
    )


async def _fill_select(page: Page, q: QuestionDict, answer: str) -> None:
    answer_lower = answer.strip().lower()

    option_value: str | None = await page.evaluate(
        """([field_name, answer_lower]) => {
            const sel = document.querySelector(`select[name='${field_name}']`);
            if (!sel) return null;
            for (const opt of sel.options) {
                if (opt.disabled) continue;
                if (opt.textContent.toLowerCase().trim().includes(answer_lower)) return opt.value;
            }
            return null;
        }""",
        [q.field_name, answer_lower],
    )

    selector = f"select[name='{q.field_name}']"
    if option_value is not None:
        await page.select_option(selector, value=option_value)
    else:
        await page.select_option(selector, label=answer)

async def _confirm_submission(job: dict) -> bool:
    """
    Pause and ask the user to confirm before submitting.
    - Press ENTER → submit
    - Type 's' + ENTER → skip this application
    The browser window stays open so the user can review the filled form.
    """
    print(
        f"\n{'─' * 60}\n"
        f"📋  Ready to submit: {job['title']} @ {job['company']}\n"
        f"🔗  {job['link']}\n"
        f"{'─' * 60}\n"
        f"Review the filled form in the browser window.\n"
        f"  [ENTER]   → Submit application\n"
        f"  [s+ENTER] → Skip this application\n"
    )
    user_input = input("Your choice: ").strip().lower()
    return user_input != "s"

async def _submit_form(page: Page) -> None:
    """Click the submit button and wait for confirmation."""
    submit_btn = page.locator("#submit").first
    await submit_btn.wait_for(state="visible", timeout=8_000)
    await submit_btn.click()
    await human_delay(2.0, 3.5)
    log.debug("Submit clicked.")