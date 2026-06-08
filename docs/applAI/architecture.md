# applAI Architecture Plan

## Goal

Create a local-first job application automation subsystem that can use Playwright to access approved job websites, log in when allowed, navigate role pages, extract role data from DOM and screenshots, draft application answers, fill forms, and help the user apply to roles with strong guardrails.

## Design Principles

- Local-first by default: prefer Ollama text and vision models so users can avoid paid services.
- Allowlist-driven browsing: the agent only navigates to configured domains and URL patterns.
- Human approval for irreversible actions: submitting applications, registering accounts, sending emails, changing passwords, or using email tokens requires explicit confirmation unless the user enables a narrow advanced policy.
- Structured tools, not shell freedom: the LLM requests actions through typed APIs such as `open_url`, `extract_role`, `fill_field`, and `find_email_token`; it does not directly control arbitrary CLI commands.
- Secrets stay outside prompts: passwords, OAuth tokens, and session cookies are read by trusted code and never included in LLM context.
- Auditable automation: every browser action, field fill, screenshot, extraction, and submit decision gets a redacted event log.

## Recommended Approach

Use a separate `applai` subsystem with a service-style controller and narrow tool APIs.

Alternative approaches considered:

- Extend the current screenshot hotkey flow: fastest to prototype, but credentials, browser sessions, and job tracking would become mixed with overlay concerns.
- Build a separate standalone app: cleaner isolation, but it would duplicate settings, provider selection, local model setup, and desktop UI work.
- Recommended: add a separate package inside this repo that reuses provider/settings concepts while keeping browser automation, secrets, and job data isolated.

## Major Components

### 1. Orchestrator

Owns the application workflow state machine:

1. Select a target site and role source.
2. Start or reuse an isolated Playwright browser context.
3. Navigate and extract role data.
4. Compare the role against the user profile and resume.
5. Draft application answers and field mappings.
6. Fill fields only when policy allows.
7. Pause for user confirmation before final submit.
8. Store outcome, screenshots, and redacted logs.

The orchestrator should be deterministic Python code. The LLM can propose next actions, but policy validation decides whether an action runs.

### 2. Browser Worker

Uses Playwright to drive Chromium with persistent browser profiles per site or per user profile.

Responsibilities:

- Launch browser with configured headless/headful mode.
- Enforce allowed domains and blocked domains.
- Navigate pages, click elements, type into fields, upload files, and capture screenshots.
- Extract DOM text, accessibility tree data, selected attributes, and form field metadata.
- Detect login walls, CAPTCHA, MFA prompts, file upload controls, and final-submit buttons.
- Return structured observations to the orchestrator.

The first version should run headful by default so users can see what is happening.

### 3. Site Registry

Stores per-site configuration:

- Allowed domains and URL patterns.
- Login URL and supported auth method.
- Role search/result URL patterns.
- Known selectors for common fields.
- Forbidden actions, such as auto-submit or account creation.
- Rate limits and pause rules.
- Notes about site-specific terms or behavior.

The registry should support generic sites with no custom selectors, then add site adapters only where necessary.

### 4. Extraction Pipeline

Combines multiple signals:

- DOM text and semantic HTML.
- Structured metadata such as JSON-LD or embedded job posting data.
- Accessibility snapshots for labels and form fields.
- Screenshots analyzed by local vision models through Ollama.
- Optional OCR if a site renders important text as images.

Output should normalize into a `RolePosting` record with title, company, location, compensation, requirements, responsibilities, application URL, source site, confidence, and extraction notes.

### 5. LLM Provider Layer

Reuses the existing local-first provider pattern:

- Text model: Ollama by default, with optional OpenAI/Codex later if configured.
- Vision model: Ollama vision model by default, with existing screenshot tiling behavior as a reference.
- Prompting style: ask for structured JSON where possible so the workflow can validate results.

The LLM should receive redacted browser observations and screenshots, not raw secrets.

### 6. Application Profile And Documents

Stores user-controlled application materials:

- Candidate profile.
- Resume files.
- Cover-letter templates.
- Work authorization answers.
- Demographic questions policy, including skip/prefer-not-to-answer behavior.
- Site-specific reusable answers.

Sensitive identity fields should be separated from general profile text and only injected into forms when a policy allows it.

### 7. Credential And Session Manager

Handles credentials without exposing them to the LLM:

- Store passwords in Windows Credential Manager through a Python keyring-compatible layer.
- Store Playwright session state separately from general logs.
- Support per-site email, username, and password references by secret key.
- Never write plaintext passwords into `settings.json`, logs, prompts, screenshots, or job records.

### 8. Email Connector

Handles verification tokens and registration emails through a scoped Gmail integration.

Recommended model:

- Use Gmail API OAuth scopes limited to reading relevant messages.
- Expose structured functions such as `find_recent_token(sender, subject_contains, received_after)` and `mark_message_used(message_id)`.
- Never let the LLM run arbitrary Gmail CLI commands.
- Never expose unrelated mailbox content to prompts.
- Log only sender, subject hash or redacted subject, timestamp, and token-use outcome.

If a Gmail CLI is used, wrap it in trusted Python code with an allowlisted command surface and JSON output.

### 9. Job Store And Audit Log

Stores durable local state:

- Role postings.
- Application drafts.
- Application status.
- Screenshots and extracted observations.
- Redacted action log.
- User approvals and timestamps.

Start with SQLite for local durability and simple querying. Keep screenshots in a local `logs/applai/` tree with redaction options.

## Data Flow

1. User chooses or imports target sites and search criteria.
2. Orchestrator validates the site against the registry.
3. Browser worker opens the site and returns observations.
4. Extraction pipeline creates `RolePosting` records.
5. LLM ranks roles against the user profile.
6. For selected roles, LLM drafts field values and a cover note.
7. Browser worker fills allowed fields.
8. User reviews visible browser state and generated answers.
9. User approves final submit.
10. Orchestrator submits, records result, and captures confirmation.

## Error Handling

- Block navigation outside allowlisted domains.
- Pause on CAPTCHA, MFA, unexpected login prompts, payment prompts, or legal/consent prompts.
- Retry transient navigation failures with bounded backoff.
- Store screenshots for failed extraction or failed form mapping.
- Mark uncertain extractions with low confidence instead of guessing.
- Require user review when the model cannot map a field confidently.

## Testing Strategy

- Unit tests for config parsing, allowlist enforcement, policy decisions, redaction, and extraction normalization.
- Playwright tests against local fixture pages for login, role extraction, form filling, blocked navigation, CAPTCHA detection, and final-submit gates.
- Integration tests with fake Gmail messages through a local fixture adapter.
- Provider tests that mock Ollama/OpenAI-compatible responses and validate structured JSON parsing.
- Manual smoke tests in headful browser mode before enabling any live-site automation.
