"""
src/platforms/naukri/selectors.py
All Naukri-specific CSS selectors.
Last verified: 2026-02-28
"""

# ── Job listing page ──────────────────────────────────────────────────────────
JOB_CARD             = ".srp-jobtuple-wrapper"
JOB_TITLE            = "h2 a.title"
JOB_COMPANY          = ".comp-name"
JOB_EXPERIENCE       = ".exp-wrap span span"
JOB_SALARY           = ".sal-wrap span span"
JOB_LOCATION         = ".loc-wrap span span"
JOB_POSTED           = ".job-post-day"

# ── Job detail page ───────────────────────────────────────────────────────────
JOB_DESCRIPTION      = ".job-desc, .jd-desc, .job-details-section"

# ── Apply / status buttons ────────────────────────────────────────────────────
APPLY_BTN            = "#apply-button"
ALREADY_APPLIED      = "#already-applied, span.already-applied"
APPLY_SUCCESS        = "span.apply-message"
WALKIN_BTN           = "#walkin-button"          # "I am interested" button
COMPANY_SITE_BTN = "#company-site-button"

# ── Chatbot (Q&A form) ────────────────────────────────────────────────────────
CHAT_LIST            = "ul[id^='chatList__']"
BOT_MESSAGES         = "li.botItem .botMsg span"
RADIO_CONTAINER      = "div[id^='singleselect_radiobutton__']"
RADIO_INPUTS         = "input[type='radio'].ssrc__radio"
TEXT_INPUT           = "div.textArea[contenteditable='true']"
SAVE_BTN             = "div.sendMsg"

# ── Pagination ────────────────────────────────────────────────────────────────
PAGINATION_NEXT      = "a.pagination-next, .pagination .next"

