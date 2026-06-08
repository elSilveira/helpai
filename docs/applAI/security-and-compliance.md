# applAI Security And Compliance Plan

## Non-Negotiable Rules

- Do not automate sites that are not explicitly allowlisted.
- Do not bypass CAPTCHA, MFA, rate limits, access controls, or anti-abuse systems.
- Do not submit applications, register accounts, send emails, or use verification tokens without a configured policy and visible user approval.
- Do not store plaintext passwords in repository files, `settings.json`, logs, screenshots metadata, prompts, or SQLite records.
- Do not expose mailbox content, passwords, cookies, or OAuth tokens to the LLM.
- Do not use applAI to spam applications or misrepresent the user.

## Threats To Design Against

### Credential Exposure

Risk: passwords, cookies, email tokens, or OAuth tokens leak into prompts, logs, screenshots, or crash reports.

Controls:

- Keep secrets in Windows Credential Manager or an equivalent OS vault.
- Use credential references in config.
- Redact sensitive fields before audit logging.
- Strip secrets from model inputs.
- Add tests that assert redaction for password, token, cookie, authorization, email-code, and session fields.

### Unapproved Site Automation

Risk: the browser follows links to third-party domains or submits data somewhere unintended.

Controls:

- Enforce allowed domains before navigation.
- Re-check domain before every click that can navigate.
- Block iframes or popups outside approved domains unless explicitly configured.
- Record blocked navigation events.

### Silent Irreversible Actions

Risk: the agent submits applications, creates accounts, changes profile data, or uses verification links without the user seeing it.

Controls:

- Model each high-impact action as a policy-gated action.
- Require user confirmation for final submit by default.
- Show the target URL, fields to be submitted, attached files, and generated answers before submit.
- Store confirmation timestamp and policy reason.

### Hallucinated Application Answers

Risk: the LLM invents experience, credentials, education, dates, authorization, salary data, or demographic answers.

Controls:

- Separate known profile facts from drafted language.
- Mark unknown answers as `requires_user_input`.
- Forbid guessing on legal, authorization, immigration, demographic, salary, education, certification, and employment-history fields.
- Add tests for unsupported answer refusal.

### Email Overreach

Risk: email integration reveals unrelated mailbox content or lets the LLM act as a general mailbox operator.

Controls:

- Use narrow Gmail scopes where practical.
- Search only recent messages from configured senders and subjects.
- Extract tokens with trusted code, not open-ended model reading.
- Never send, delete, archive, or globally label messages in the first implementation.
- Validate confirmation links against the active site's allowlist.

### Site Abuse And Account Risk

Risk: high-volume automation violates terms, locks accounts, or creates abusive traffic.

Controls:

- Per-site rate limits.
- Maximum roles/applications per run.
- Randomness is not a compliance strategy; use clear slow, bounded, user-visible automation.
- Pause on CAPTCHA, bot challenge, suspicious activity prompts, or account warnings.
- Keep first live pilots small and headful.

## Audit Requirements

Each run should record:

- Run ID, profile ID, site ID, mode, and timestamp.
- Allowed-domain decisions.
- Browser actions with redacted values.
- Screenshots or screenshot paths.
- Extracted role record and confidence.
- Drafted answers and source facts used.
- User approvals and rejected actions.
- Submit result or failure state.

Logs should be local by default and should have a delete/export path later.

## Policy Defaults

Default settings should be conservative:

- applAI disabled.
- Headful browser.
- Read-only observe mode.
- Gmail disabled.
- Account registration disabled.
- Password entry disabled until a credential reference is configured.
- Submit disabled until the user confirms in the UI.
- Cloud AI providers disabled unless the user opts in.

## Compliance Notes

Before adding a site adapter, document the site's automation constraints in the site registry. If a site forbids automated application submission, applAI should stay in observe/draft mode for that site. The user can still use generated answers manually when appropriate.

The product should describe itself as assisted application automation, not guaranteed mass application automation. That framing matches the required safety and reliability model.
