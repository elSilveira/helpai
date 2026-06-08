# applAI Implementation Roadmap

## Phase 0: Decisions Before Coding

- Confirm the first target workflow: job-board search, company career page, or applicant-tracking-system form.
- Confirm whether first release is headful desktop-only on Windows.
- Confirm storage choice: SQLite for job state and JSON for settings.
- Confirm initial local models to support through Ollama.
- Confirm whether Gmail integration starts as a fake/local fixture before live OAuth.

Recommended first target: headful browser automation for one allowlisted demo site or local fixture site, with extraction and draft generation, no live submission.

## Phase 1: Package Boundary And Data Models

Create a new `applai` package.

Proposed files:

- `applai/__init__.py`: package marker and version metadata.
- `applai/models.py`: dataclasses or Pydantic-style models for sites, roles, profiles, applications, actions, and policy decisions.
- `applai/settings.py`: load/save applAI-specific settings and merge defaults.
- `applai/policy.py`: allowlist, action gating, confirmation requirements, and redaction rules.
- `tests/test_applai_policy.py`: policy unit tests.
- `tests/test_applai_settings.py`: config parsing and migration tests.

Acceptance criteria:

- A site outside the allowlist is blocked.
- A final submit action requires confirmation by default.
- Password and token fields are redacted from logs.
- Settings load without changing the existing HelpAI settings behavior.

## Phase 2: Playwright Browser Worker

Add Playwright as an optional dependency and implement browser control behind a narrow API.

Proposed files:

- `applai/browser_worker.py`: launch browser, manage contexts, navigate, click, type, upload, screenshot, and extract observations.
- `applai/browser_types.py`: browser observation and action result models.
- `tests/fixtures/applai_site/`: local HTML pages for role listings, login, application forms, and confirmation screens.
- `tests/test_applai_browser_worker.py`: tests against local fixture pages.

Acceptance criteria:

- Browser opens in headful mode by default.
- Navigation to unapproved domains is blocked before Playwright loads the page.
- The worker can extract title, URL, visible text, links, buttons, inputs, and a screenshot from a fixture page.
- The worker detects final-submit-like buttons and labels them as gated actions.

## Phase 3: Extraction Pipeline

Normalize role pages into structured records.

Proposed files:

- `applai/extraction.py`: DOM, metadata, accessibility, and screenshot extraction merger.
- `applai/llm.py`: local provider wrapper for structured text/vision extraction.
- `applai/prompts.py`: prompts for role extraction, form mapping, answer drafting, and screenshot interpretation.
- `tests/test_applai_extraction.py`: parsing and normalization tests with fixture HTML.
- `tests/test_applai_llm_contracts.py`: mocked LLM response parsing tests.

Acceptance criteria:

- Extracts title, company, location, requirements, responsibilities, apply URL, and confidence from fixture pages.
- Handles missing fields by returning low confidence and extraction notes.
- Parses model JSON safely and rejects malformed or incomplete responses.
- Uses local Ollama settings without requiring OpenAI keys.

## Phase 4: Application Drafting And Profile Matching

Generate user-reviewable application drafts.

Proposed files:

- `applai/profile_store.py`: load candidate profile and resume references.
- `applai/ranking.py`: score role fit against profile.
- `applai/application_draft.py`: generate cover notes, field answers, and resume selection.
- `tests/test_applai_application_draft.py`: deterministic draft behavior with mocked LLM output.

Acceptance criteria:

- Produces a role-fit summary and application recommendation.
- Drafts answers without inventing credentials, education, dates, or work history.
- Marks uncertain answers as requiring user input.
- Applies configured answer policy for salary, sponsorship, demographic, and EEO questions.

## Phase 5: Form Mapping And Assisted Fill

Map application forms to profile data and draft answers.

Proposed files:

- `applai/form_mapper.py`: map labels/placeholders/options to profile fields.
- `applai/form_fill.py`: execute safe fills through browser worker.
- `tests/test_applai_form_mapper.py`: fixture form mapping tests.
- `tests/test_applai_form_fill.py`: fill actions against local fixture pages.

Acceptance criteria:

- Text inputs, textareas, selects, radio buttons, checkboxes, and file uploads are represented in a structured form model.
- Low-confidence field mappings pause for user review.
- Submit buttons are detected but not clicked without confirmation.
- Filled values are logged with redaction for sensitive fields.

## Phase 6: Credentials And Login

Add login support without exposing secrets to the LLM.

Proposed files:

- `applai/secrets.py`: Windows credential manager/keyring adapter.
- `applai/login.py`: site login state machine.
- `tests/test_applai_secrets.py`: secret reference and redaction tests with a fake backend.
- `tests/test_applai_login.py`: fixture login flow tests.

Acceptance criteria:

- Passwords are referenced by key and never written to settings or logs.
- Login only runs for configured allowed domains.
- MFA, CAPTCHA, and unexpected login flows pause for user action.
- Browser session storage can be saved and reused per site.

## Phase 7: Gmail Token Connector

Add email token retrieval through a safe structured connector.

Proposed files:

- `applai/email/__init__.py`: email connector package.
- `applai/email/gmail.py`: Gmail API or wrapped CLI adapter.
- `applai/email/token_extract.py`: trusted token and confirmation-link parser.
- `tests/test_applai_email_token_extract.py`: parser tests.
- `tests/test_applai_gmail_connector.py`: fake Gmail adapter tests.

Acceptance criteria:

- Connector can search only recent allowed-sender messages.
- Extracts verification code or link without passing full mailbox content to the LLM.
- Validates confirmation links against the active site's allowed domains.
- Requires policy permission before using email tokens.

## Phase 8: Job Store And Audit

Persist role records, application state, screenshots, and redacted action logs.

Proposed files:

- `applai/store.py`: SQLite store and schema migrations.
- `applai/audit.py`: redacted event logging.
- `tests/test_applai_store.py`: persistence tests.
- `tests/test_applai_audit.py`: redaction and event-shape tests.

Acceptance criteria:

- Every role has a durable ID, source URL, extraction timestamp, and status.
- Every sensitive event is redacted.
- Screenshots are linked from records without embedding image bytes in SQLite.
- Failed runs can be resumed or inspected.

## Phase 9: UI And User Controls

Expose applAI controls through a simple settings panel or a separate launcher window.

Proposed files:

- `applai/ui.py`: first-pass Tkinter control surface or integration hooks.
- `tests/test_applai_ui_settings.py`: settings serialization tests.

Acceptance criteria:

- User can enable applAI, configure local Ollama models, add allowed sites, and choose runtime mode.
- User can add a profile and resume path.
- User can start observe/draft/assist runs.
- User can approve or reject final submission.

## Phase 10: Live-Site Pilot

Run one carefully selected live-site pilot after local fixture tests pass.

Pilot rules:

- Use a user-owned account.
- Use headful mode.
- Use one allowlisted site only.
- Keep final submit disabled for the first pilot.
- Capture logs and screenshots locally.
- Review site terms and robots guidance before enabling automation.

Success criteria:

- Login succeeds or pauses safely.
- Role extraction produces accurate structured data.
- Form mapping is correct or pauses on uncertainty.
- No off-allowlist navigation occurs.
- No final application is submitted without explicit approval.
