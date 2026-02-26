"""
src/platforms/internshala/selectors.py
All Internshala-specific CSS selectors and XPath expressions.
Centralizing selectors here makes updates easy when the site changes.

NOTE: These selectors are based on Internshala's structure as of mid-2025.
      Verify and update if the site changes layout.
"""

# ── Job listing page ──────────────────────────────────────────────────────────
JOB_CARD = ".individual_internship"                     # each job card container
JOB_TITLE = ".job-internship-name"                      # role title link
JOB_COMPANY = ".company-name"                           # company name
JOB_LOCATION = ".location_link, .locations_link"        # location text
JOB_STIPEND = ".stipend"                                # stipend / salary
JOB_DURATION = ".item_body.internship_other_details_container .item_body"  # duration
JOB_POSTED = ".status-inactive, .posted-on"             # days ago posted
JOB_LINK_ATTR = "href"      

# attribute to get link from title anchor

# ── Job detail page ───────────────────────────────────────────────────────────
JOB_DESCRIPTION = "#about_internship, .about-section, .internship_details"
JOB_APPLY_BTN = "#apply_button, .apply_button, button:has-text('Apply')"

# ── Application modal / form ──────────────────────────────────────────────────
APPLICATION_MODAL = "#application_modal, .application-modal"
APPLICATION_FORM = "#application_form, form.application"
FORM_QUESTION_CONTAINER = ".question"
QUESTION_LABEL = ".question_label, label"
QUESTION_INPUT_TEXT = "input[type='text'], textarea"
QUESTION_INPUT_RADIO = "input[type='radio']"
QUESTION_INPUT_CHECKBOX = "input[type='checkbox']"
QUESTION_SELECT = "select"
FORM_SUBMIT_BTN = "#submit, button[type='submit'], .submit_button"

# ── Login page ────────────────────────────────────────────────────────────────
LOGIN_EMAIL = "#email, input[name='email']"
LOGIN_PASSWORD = "#password, input[name='password']"
LOGIN_SUBMIT = "#login_submit, button[type='submit']"

# ── Pagination ────────────────────────────────────────────────────────────────
PAGINATION_NEXT = "a.next_page, .pagination .next a"
