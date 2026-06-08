# applAI Configuration Plan

## Configuration Storage

Use a dedicated `applai` settings section or a separate `applai_settings.json` file. Keep regular preferences in JSON, but store secrets in the OS credential vault.

Recommended top-level shape:

```json
{
  "enabled": false,
  "browser": {
    "headless": false,
    "slow_mo_ms": 50,
    "user_data_dir": "logs/applai/browser-profiles/default",
    "downloads_dir": "logs/applai/downloads",
    "screenshot_dir": "logs/applai/screenshots"
  },
  "models": {
    "text_provider": "ollama",
    "vision_provider": "ollama",
    "ollama_base_url": "http://localhost:11434",
    "ollama_text_model": "qwen3:8b",
    "ollama_vision_model": "gemma3:12b",
    "prefer_cuda": true
  },
  "policy": {
    "require_confirmation_before_submit": true,
    "allow_account_registration": false,
    "allow_email_token_read": false,
    "allow_password_entry": false,
    "max_applications_per_run": 5,
    "min_seconds_between_site_actions": 2
  },
  "sites": [],
  "profiles": []
}
```

## Site Allowlist

Every site must be explicitly configured. A site entry should include allowed domains, blocked domains, login behavior, and automation policy.

```json
{
  "id": "example-careers",
  "name": "Example Careers",
  "allowed_domains": ["careers.example.com", "jobs.example.com"],
  "blocked_domains": ["ads.example.com", "tracking.example.com"],
  "start_urls": ["https://careers.example.com/search"],
  "login": {
    "enabled": true,
    "login_url": "https://careers.example.com/login",
    "credential_ref": "applai/example-careers/main",
    "requires_email_token": true
  },
  "automation": {
    "allow_read": true,
    "allow_form_fill": true,
    "allow_submit": false,
    "allow_register": false
  },
  "rate_limit": {
    "min_seconds_between_actions": 2,
    "max_roles_per_run": 20,
    "max_applications_per_run": 3
  }
}
```

## Credentials

Do not store passwords in JSON. Store only credential references:

```json
{
  "site_id": "example-careers",
  "username": "candidate@example.com",
  "password_ref": "applai/example-careers/main-password"
}
```

Implementation target:

- Use Windows Credential Manager through `keyring` or a thin Win32 wrapper.
- Store OAuth tokens under separate key names.
- Redact usernames when logs leave the local machine.
- Never pass passwords or tokens to the LLM.

## Gmail And Email Tokens

The Gmail integration should be disabled by default. When enabled, it should use a narrow structured interface.

Recommended config:

```json
{
  "email": {
    "provider": "gmail",
    "enabled": false,
    "oauth_credential_ref": "applai/gmail/oauth",
    "allowed_senders": ["no-reply@example.com"],
    "allowed_subject_contains": ["verification", "security code", "one-time code"],
    "max_message_age_minutes": 30,
    "expose_message_body_to_llm": false
  }
}
```

Allowed email operations:

- Search recent mail from allowed senders.
- Extract one-time token or confirmation link through trusted regex/parser code.
- Open a confirmation link only after domain validation.
- Mark a token as used in local state.

Blocked email operations:

- Reading arbitrary mailbox content.
- Sending emails without user confirmation.
- Deleting messages.
- Changing mailbox labels globally.
- Letting the LLM run arbitrary Gmail CLI commands.

## Application Profile

Store user application data in a profile file or SQLite table. Separate general career facts from high-sensitivity identity fields.

```json
{
  "id": "default",
  "display_name": "Default Profile",
  "resume_path": "C:/Users/duzit/Documents/resume.pdf",
  "target_roles": ["Software Engineer", "AI Engineer"],
  "locations": ["Remote", "United States"],
  "work_authorization": {
    "requires_sponsorship": false,
    "authorized_to_work_us": true
  },
  "answer_policy": {
    "salary_expectation": "ask_user",
    "demographics": "prefer_not_to_answer",
    "eeo_questions": "prefer_not_to_answer",
    "custom_questions": "draft_then_confirm"
  }
}
```

## Local Ollama With CUDA

applAI should reuse the existing Ollama base URL and model settings where possible, but add job-automation-specific model choices if needed.

Recommended behavior:

- Detect Ollama availability on startup.
- Detect configured model availability before running.
- Offer pull commands for missing models instead of silently falling back to paid providers.
- Prefer GPU through the installed Ollama runtime and CUDA drivers; do not manage GPU memory directly from applAI.
- Keep cloud providers opt-in.

Suggested local model split:

- Text reasoning and form drafting: `qwen3:8b` or larger local model depending on available VRAM.
- Vision extraction: `gemma3:12b` or another installed Ollama vision-capable model.
- Embedding/ranking later: local embedding model only after the first workflow is stable.

## Runtime Modes

- `observe`: navigate and extract only.
- `draft`: extract roles and draft application answers.
- `assist`: fill forms but pause before submit.
- `advanced_auto`: submit only on sites where the user explicitly enabled auto-submit and where site policy allows it.

The default mode should be `observe` until a user configures a profile and site policy.
