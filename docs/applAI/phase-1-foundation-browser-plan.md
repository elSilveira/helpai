# applAI Foundation Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first safe applAI slice: package boundary, local settings, allowlist policy, redacted audit events, and read-only Playwright navigation against local fixtures.

**Architecture:** Add a new `applai` package inside the existing Python project. Keep browser automation behind typed Python APIs and policy checks so later login, Gmail, and application submission work cannot bypass allowlist and confirmation rules. Use local fixture pages for browser tests; no live-site automation is part of this phase.

**Tech Stack:** Python 3.11+, `unittest`, dataclasses, JSON settings, optional `playwright>=1.44.0`, existing setuptools packaging.

---

## Scope

This plan implements:

- New `applai` package.
- Data models for sites, policies, browser actions, browser observations, and audit events.
- Local JSON settings loader for applAI defaults.
- Policy checks for navigation, form filling, submit gating, password entry gating, and email-token gating.
- Redaction for audit payloads.
- Playwright browser worker in read-only mode.
- Local fixture pages for deterministic tests.

This plan does not implement:

- Live job-board automation.
- Credential vault integration.
- Gmail OAuth or Gmail CLI integration.
- Application answer drafting.
- Form filling on real sites.
- Final application submission.

## File Structure

- Create `applai/__init__.py`: package export surface.
- Create `applai/models.py`: dataclasses and enums shared by settings, policy, audit, and browser code.
- Create `applai/settings.py`: load and save applAI settings without modifying the existing app settings file.
- Create `applai/policy.py`: allowlist and action gating.
- Create `applai/audit.py`: redacted audit event construction.
- Create `applai/browser_worker.py`: Playwright wrapper with read-only navigation and extraction.
- Create `tests/test_applai_models.py`: model normalization tests.
- Create `tests/test_applai_settings.py`: settings loader tests.
- Create `tests/test_applai_policy.py`: allowlist and confirmation-gate tests.
- Create `tests/test_applai_audit.py`: redaction tests.
- Create `tests/test_applai_browser_worker.py`: local fixture browser tests, skipped when Playwright is not installed.
- Create `tests/fixtures/applai_site/index.html`: listing fixture.
- Create `tests/fixtures/applai_site/role.html`: role fixture.
- Modify `pyproject.toml`: include the new package and an optional `applai` dependency group.

## Task 1: Package Models

**Files:**
- Create: `applai/__init__.py`
- Create: `applai/models.py`
- Test: `tests/test_applai_models.py`

- [ ] **Step 1: Write the failing model tests**

Create `tests/test_applai_models.py`:

```python
import unittest

from applai.models import (
    ActionKind,
    ApplAISettings,
    BrowserAction,
    BrowserObservation,
    SiteConfig,
    SitePolicy,
)


class ApplAIModelTests(unittest.TestCase):
    def test_site_config_normalizes_domains_and_defaults_policy(self):
        site = SiteConfig(
            id="example",
            name="Example Jobs",
            allowed_domains=["Careers.Example.com", " jobs.example.com "],
            start_urls=["https://careers.example.com/search"],
        )

        self.assertEqual(site.allowed_domains, ("careers.example.com", "jobs.example.com"))
        self.assertFalse(site.policy.allow_submit)
        self.assertTrue(site.policy.allow_read)

    def test_settings_find_site_by_id(self):
        site = SiteConfig(
            id="example",
            name="Example Jobs",
            allowed_domains=["careers.example.com"],
            start_urls=["https://careers.example.com/search"],
        )
        settings = ApplAISettings(sites=(site,))

        self.assertIs(settings.site_by_id("example"), site)
        self.assertIsNone(settings.site_by_id("missing"))

    def test_browser_action_marks_sensitive_values(self):
        action = BrowserAction(
            kind=ActionKind.TYPE_TEXT,
            url="https://careers.example.com/login",
            selector="#password",
            value="secret-password",
            sensitive=True,
        )

        self.assertTrue(action.sensitive)
        self.assertEqual(action.kind, ActionKind.TYPE_TEXT)

    def test_observation_keeps_structured_page_data(self):
        observation = BrowserObservation(
            url="https://careers.example.com/role",
            title="Senior AI Engineer",
            visible_text="Build local AI tooling",
            links=("https://careers.example.com/apply",),
            buttons=("Apply",),
            inputs=("email", "resume"),
            screenshot_path="logs/applai/screenshots/role.png",
        )

        self.assertIn("local AI", observation.visible_text)
        self.assertEqual(observation.buttons, ("Apply",))

    def test_policy_defaults_are_conservative(self):
        policy = SitePolicy()

        self.assertTrue(policy.allow_read)
        self.assertFalse(policy.allow_form_fill)
        self.assertFalse(policy.allow_submit)
        self.assertFalse(policy.allow_register)
        self.assertFalse(policy.allow_password_entry)
        self.assertFalse(policy.allow_email_token_read)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the model tests and verify failure**

Run:

```powershell
python -m unittest tests.test_applai_models -v
```

Expected: fails with `ModuleNotFoundError: No module named 'applai'`.

- [ ] **Step 3: Create package marker**

Create `applai/__init__.py`:

```python
"""applAI assisted job-application automation package."""

from applai.models import (
    ActionDecision,
    ActionKind,
    ApplAISettings,
    BrowserAction,
    BrowserObservation,
    SiteConfig,
    SitePolicy,
)

__all__ = [
    "ActionDecision",
    "ActionKind",
    "ApplAISettings",
    "BrowserAction",
    "BrowserObservation",
    "SiteConfig",
    "SitePolicy",
]
```

- [ ] **Step 4: Implement models**

Create `applai/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ActionKind(str, Enum):
    NAVIGATE = "navigate"
    READ_PAGE = "read_page"
    CLICK = "click"
    TYPE_TEXT = "type_text"
    UPLOAD_FILE = "upload_file"
    SUBMIT = "submit"
    READ_EMAIL_TOKEN = "read_email_token"
    REGISTER_ACCOUNT = "register_account"


@dataclass(frozen=True)
class SitePolicy:
    allow_read: bool = True
    allow_form_fill: bool = False
    allow_submit: bool = False
    allow_register: bool = False
    allow_password_entry: bool = False
    allow_email_token_read: bool = False
    require_confirmation_before_submit: bool = True
    min_seconds_between_actions: float = 2.0
    max_roles_per_run: int = 20
    max_applications_per_run: int = 3


@dataclass(frozen=True)
class SiteConfig:
    id: str
    name: str
    allowed_domains: tuple[str, ...] | list[str]
    start_urls: tuple[str, ...] | list[str] = field(default_factory=tuple)
    blocked_domains: tuple[str, ...] | list[str] = field(default_factory=tuple)
    policy: SitePolicy = field(default_factory=SitePolicy)

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_domains", _normalize_domains(self.allowed_domains))
        object.__setattr__(self, "blocked_domains", _normalize_domains(self.blocked_domains))
        object.__setattr__(self, "start_urls", tuple(url.strip() for url in self.start_urls if url.strip()))


@dataclass(frozen=True)
class ApplAISettings:
    enabled: bool = False
    text_provider: str = "ollama"
    vision_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_text_model: str = "qwen3:8b"
    ollama_vision_model: str = "gemma3:12b"
    headless: bool = False
    slow_mo_ms: int = 50
    screenshot_dir: str = "logs/applai/screenshots"
    sites: tuple[SiteConfig, ...] = field(default_factory=tuple)

    def site_by_id(self, site_id: str) -> SiteConfig | None:
        for site in self.sites:
            if site.id == site_id:
                return site
        return None


@dataclass(frozen=True)
class BrowserAction:
    kind: ActionKind
    url: str = ""
    selector: str = ""
    value: str = ""
    sensitive: bool = False
    requires_confirmation: bool = False


@dataclass(frozen=True)
class BrowserObservation:
    url: str
    title: str
    visible_text: str
    links: tuple[str, ...] = field(default_factory=tuple)
    buttons: tuple[str, ...] = field(default_factory=tuple)
    inputs: tuple[str, ...] = field(default_factory=tuple)
    screenshot_path: str = ""


@dataclass(frozen=True)
class ActionDecision:
    allowed: bool
    reason: str
    requires_confirmation: bool = False


def _normalize_domains(domains: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for domain in domains:
        value = domain.strip().lower()
        if value:
            normalized.append(value)
    return tuple(normalized)
```

- [ ] **Step 5: Run the model tests and verify pass**

Run:

```powershell
python -m unittest tests.test_applai_models -v
```

Expected: all 5 tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add applai/__init__.py applai/models.py tests/test_applai_models.py
git commit -m "feat: add applai foundation models"
```

Expected: commit succeeds.

## Task 2: Settings Loader

**Files:**
- Create: `applai/settings.py`
- Test: `tests/test_applai_settings.py`

- [ ] **Step 1: Write the failing settings tests**

Create `tests/test_applai_settings.py`:

```python
import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from applai.models import SitePolicy
from applai.settings import load_settings, save_settings


class ApplAISettingsTests(unittest.TestCase):
    def _tmp_dir(self) -> Path:
        path = Path("build_temp") / f"test-applai-settings-{uuid4().hex}"
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_load_missing_file_returns_conservative_defaults(self):
        settings = load_settings(self._tmp_dir() / "applai_settings.json")

        self.assertFalse(settings.enabled)
        self.assertEqual(settings.text_provider, "ollama")
        self.assertEqual(settings.vision_provider, "ollama")
        self.assertEqual(settings.sites, ())

    def test_load_site_policy_from_json(self):
        path = self._tmp_dir() / "applai_settings.json"
        path.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "browser": {"headless": True, "slow_mo_ms": 0},
                    "models": {
                        "text_provider": "ollama",
                        "vision_provider": "ollama",
                        "ollama_base_url": "http://localhost:11434",
                        "ollama_text_model": "qwen3:8b",
                        "ollama_vision_model": "gemma3:12b",
                    },
                    "sites": [
                        {
                            "id": "example",
                            "name": "Example Jobs",
                            "allowed_domains": ["careers.example.com"],
                            "blocked_domains": ["tracking.example.com"],
                            "start_urls": ["https://careers.example.com/search"],
                            "policy": {
                                "allow_form_fill": True,
                                "allow_submit": False,
                                "allow_password_entry": True,
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        settings = load_settings(path)

        self.assertTrue(settings.enabled)
        self.assertTrue(settings.headless)
        self.assertEqual(settings.slow_mo_ms, 0)
        self.assertEqual(settings.site_by_id("example").policy.allow_form_fill, True)
        self.assertEqual(settings.site_by_id("example").blocked_domains, ("tracking.example.com",))

    def test_save_settings_round_trips_without_secrets(self):
        path = self._tmp_dir() / "applai_settings.json"
        settings = load_settings(path)

        save_settings(path, settings)

        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(raw["models"]["text_provider"], "ollama")
        self.assertNotIn("password", json.dumps(raw).lower())
        self.assertNotIn("token", json.dumps(raw).lower())

    def test_unknown_policy_keys_are_ignored(self):
        path = self._tmp_dir() / "applai_settings.json"
        path.write_text(
            json.dumps(
                {
                    "sites": [
                        {
                            "id": "example",
                            "name": "Example Jobs",
                            "allowed_domains": ["careers.example.com"],
                            "policy": {
                                "allow_read": True,
                                "unknown_key": "ignored",
                            },
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        settings = load_settings(path)

        self.assertIsInstance(settings.site_by_id("example").policy, SitePolicy)
        self.assertTrue(settings.site_by_id("example").policy.allow_read)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the settings tests and verify failure**

Run:

```powershell
python -m unittest tests.test_applai_settings -v
```

Expected: fails with `ModuleNotFoundError: No module named 'applai.settings'`.

- [ ] **Step 3: Implement settings loader**

Create `applai/settings.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from applai.models import ApplAISettings, SiteConfig, SitePolicy


DEFAULT_SETTINGS_PATH = Path("applai_settings.json")


def load_settings(path: Path | str = DEFAULT_SETTINGS_PATH) -> ApplAISettings:
    settings_path = Path(path)
    if not settings_path.exists():
        return ApplAISettings()

    raw = json.loads(settings_path.read_text(encoding="utf-8"))
    browser = raw.get("browser", {})
    models = raw.get("models", {})

    return ApplAISettings(
        enabled=bool(raw.get("enabled", False)),
        text_provider=str(models.get("text_provider", "ollama")),
        vision_provider=str(models.get("vision_provider", "ollama")),
        ollama_base_url=str(models.get("ollama_base_url", "http://localhost:11434")).rstrip("/"),
        ollama_text_model=str(models.get("ollama_text_model", "qwen3:8b")),
        ollama_vision_model=str(models.get("ollama_vision_model", "gemma3:12b")),
        headless=bool(browser.get("headless", False)),
        slow_mo_ms=int(browser.get("slow_mo_ms", 50)),
        screenshot_dir=str(browser.get("screenshot_dir", "logs/applai/screenshots")),
        sites=tuple(_site_from_raw(item) for item in raw.get("sites", [])),
    )


def save_settings(path: Path | str, settings: ApplAISettings) -> None:
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    raw = {
        "enabled": settings.enabled,
        "browser": {
            "headless": settings.headless,
            "slow_mo_ms": settings.slow_mo_ms,
            "screenshot_dir": settings.screenshot_dir,
        },
        "models": {
            "text_provider": settings.text_provider,
            "vision_provider": settings.vision_provider,
            "ollama_base_url": settings.ollama_base_url,
            "ollama_text_model": settings.ollama_text_model,
            "ollama_vision_model": settings.ollama_vision_model,
        },
        "sites": [_site_to_raw(site) for site in settings.sites],
    }
    settings_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")


def _site_from_raw(raw: dict[str, Any]) -> SiteConfig:
    policy_raw = raw.get("policy", {})
    policy_fields = {field.name for field in fields(SitePolicy)}
    filtered_policy = {key: value for key, value in policy_raw.items() if key in policy_fields}
    return SiteConfig(
        id=str(raw["id"]),
        name=str(raw["name"]),
        allowed_domains=tuple(raw.get("allowed_domains", [])),
        blocked_domains=tuple(raw.get("blocked_domains", [])),
        start_urls=tuple(raw.get("start_urls", [])),
        policy=SitePolicy(**filtered_policy),
    )


def _site_to_raw(site: SiteConfig) -> dict[str, Any]:
    return {
        "id": site.id,
        "name": site.name,
        "allowed_domains": list(site.allowed_domains),
        "blocked_domains": list(site.blocked_domains),
        "start_urls": list(site.start_urls),
        "policy": asdict(site.policy),
    }
```

- [ ] **Step 4: Run settings tests and verify pass**

Run:

```powershell
python -m unittest tests.test_applai_settings -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add applai/settings.py tests/test_applai_settings.py
git commit -m "feat: add applai settings loader"
```

Expected: commit succeeds.

## Task 3: Policy Gates

**Files:**
- Create: `applai/policy.py`
- Test: `tests/test_applai_policy.py`

- [ ] **Step 1: Write the failing policy tests**

Create `tests/test_applai_policy.py`:

```python
import unittest

from applai.models import ActionKind, BrowserAction, SiteConfig, SitePolicy
from applai.policy import decide_action


class ApplAIPolicyTests(unittest.TestCase):
    def _site(self, **policy_overrides):
        return SiteConfig(
            id="example",
            name="Example Jobs",
            allowed_domains=("careers.example.com",),
            blocked_domains=("tracking.example.com",),
            policy=SitePolicy(**policy_overrides),
        )

    def test_allows_navigation_to_allowed_domain(self):
        decision = decide_action(
            self._site(),
            BrowserAction(kind=ActionKind.NAVIGATE, url="https://careers.example.com/role/1"),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "allowed")

    def test_blocks_navigation_to_unlisted_domain(self):
        decision = decide_action(
            self._site(),
            BrowserAction(kind=ActionKind.NAVIGATE, url="https://evil.example.net/role/1"),
        )

        self.assertFalse(decision.allowed)
        self.assertIn("not allowlisted", decision.reason)

    def test_blocks_navigation_to_blocked_subdomain(self):
        decision = decide_action(
            self._site(),
            BrowserAction(kind=ActionKind.NAVIGATE, url="https://tracking.example.com/pixel"),
        )

        self.assertFalse(decision.allowed)
        self.assertIn("blocked", decision.reason)

    def test_submit_requires_confirmation_even_when_site_allows_submit(self):
        decision = decide_action(
            self._site(allow_form_fill=True, allow_submit=True),
            BrowserAction(kind=ActionKind.SUBMIT, url="https://careers.example.com/apply"),
        )

        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_confirmation)

    def test_submit_is_blocked_when_site_disallows_submit(self):
        decision = decide_action(
            self._site(allow_form_fill=True, allow_submit=False),
            BrowserAction(kind=ActionKind.SUBMIT, url="https://careers.example.com/apply"),
        )

        self.assertFalse(decision.allowed)
        self.assertIn("submit disabled", decision.reason)

    def test_password_entry_requires_policy_flag(self):
        decision = decide_action(
            self._site(allow_form_fill=True, allow_password_entry=False),
            BrowserAction(
                kind=ActionKind.TYPE_TEXT,
                url="https://careers.example.com/login",
                selector="#password",
                value="secret",
                sensitive=True,
            ),
        )

        self.assertFalse(decision.allowed)
        self.assertIn("password entry disabled", decision.reason)

    def test_email_token_read_requires_policy_flag(self):
        decision = decide_action(
            self._site(allow_email_token_read=False),
            BrowserAction(kind=ActionKind.READ_EMAIL_TOKEN, url="https://careers.example.com/login"),
        )

        self.assertFalse(decision.allowed)
        self.assertIn("email token read disabled", decision.reason)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the policy tests and verify failure**

Run:

```powershell
python -m unittest tests.test_applai_policy -v
```

Expected: fails with `ModuleNotFoundError: No module named 'applai.policy'`.

- [ ] **Step 3: Implement policy gates**

Create `applai/policy.py`:

```python
from __future__ import annotations

from urllib.parse import urlparse

from applai.models import ActionDecision, ActionKind, BrowserAction, SiteConfig


def decide_action(site: SiteConfig, action: BrowserAction) -> ActionDecision:
    domain_decision = _decide_domain(site, action.url)
    if not domain_decision.allowed:
        return domain_decision

    policy = site.policy

    if action.kind == ActionKind.NAVIGATE:
        return ActionDecision(True, "allowed")

    if action.kind == ActionKind.READ_PAGE:
        if policy.allow_read:
            return ActionDecision(True, "allowed")
        return ActionDecision(False, "read disabled")

    if action.kind in {ActionKind.CLICK, ActionKind.TYPE_TEXT, ActionKind.UPLOAD_FILE}:
        if not policy.allow_form_fill:
            return ActionDecision(False, "form fill disabled")
        if action.sensitive and not policy.allow_password_entry:
            return ActionDecision(False, "password entry disabled")
        return ActionDecision(True, "allowed")

    if action.kind == ActionKind.SUBMIT:
        if not policy.allow_submit:
            return ActionDecision(False, "submit disabled")
        return ActionDecision(
            True,
            "allowed",
            requires_confirmation=policy.require_confirmation_before_submit,
        )

    if action.kind == ActionKind.READ_EMAIL_TOKEN:
        if not policy.allow_email_token_read:
            return ActionDecision(False, "email token read disabled")
        return ActionDecision(True, "allowed", requires_confirmation=True)

    if action.kind == ActionKind.REGISTER_ACCOUNT:
        if not policy.allow_register:
            return ActionDecision(False, "account registration disabled")
        return ActionDecision(True, "allowed", requires_confirmation=True)

    return ActionDecision(False, f"unsupported action: {action.kind.value}")


def _decide_domain(site: SiteConfig, url: str) -> ActionDecision:
    host = urlparse(url).hostname
    if not host:
        return ActionDecision(False, "missing URL host")

    host = host.lower()
    if _domain_matches(host, site.blocked_domains):
        return ActionDecision(False, f"domain blocked: {host}")

    if not _domain_matches(host, site.allowed_domains):
        return ActionDecision(False, f"domain not allowlisted: {host}")

    return ActionDecision(True, "allowed")


def _domain_matches(host: str, domains: tuple[str, ...]) -> bool:
    for domain in domains:
        if host == domain or host.endswith(f".{domain}"):
            return True
    return False
```

- [ ] **Step 4: Run policy tests and verify pass**

Run:

```powershell
python -m unittest tests.test_applai_policy -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add applai/policy.py tests/test_applai_policy.py
git commit -m "feat: add applai policy gates"
```

Expected: commit succeeds.

## Task 4: Audit Redaction

**Files:**
- Create: `applai/audit.py`
- Test: `tests/test_applai_audit.py`

- [ ] **Step 1: Write the failing audit tests**

Create `tests/test_applai_audit.py`:

```python
import unittest

from applai.audit import make_audit_event, redact_value
from applai.models import ActionDecision, ActionKind, BrowserAction


class ApplAIAuditTests(unittest.TestCase):
    def test_redacts_sensitive_value_by_key_name(self):
        self.assertEqual(redact_value("password", "secret"), "[REDACTED]")
        self.assertEqual(redact_value("email_token", "123456"), "[REDACTED]")
        self.assertEqual(redact_value("authorization", "Bearer abc"), "[REDACTED]")

    def test_keeps_non_sensitive_value(self):
        self.assertEqual(redact_value("title", "Senior Engineer"), "Senior Engineer")

    def test_audit_event_redacts_sensitive_action_value(self):
        event = make_audit_event(
            run_id="run-1",
            site_id="example",
            action=BrowserAction(
                kind=ActionKind.TYPE_TEXT,
                url="https://careers.example.com/login",
                selector="#password",
                value="secret-password",
                sensitive=True,
            ),
            decision=ActionDecision(False, "password entry disabled"),
        )

        self.assertEqual(event["action"]["value"], "[REDACTED]")
        self.assertEqual(event["decision"]["allowed"], False)
        self.assertNotIn("secret-password", str(event))

    def test_audit_event_keeps_non_sensitive_selector_and_url(self):
        event = make_audit_event(
            run_id="run-1",
            site_id="example",
            action=BrowserAction(
                kind=ActionKind.NAVIGATE,
                url="https://careers.example.com/role/1",
                selector="",
                value="",
            ),
            decision=ActionDecision(True, "allowed"),
        )

        self.assertEqual(event["action"]["url"], "https://careers.example.com/role/1")
        self.assertEqual(event["decision"]["reason"], "allowed")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run audit tests and verify failure**

Run:

```powershell
python -m unittest tests.test_applai_audit -v
```

Expected: fails with `ModuleNotFoundError: No module named 'applai.audit'`.

- [ ] **Step 3: Implement audit helpers**

Create `applai/audit.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from applai.models import ActionDecision, BrowserAction


SENSITIVE_KEY_PARTS = (
    "password",
    "token",
    "cookie",
    "authorization",
    "secret",
    "credential",
)


def redact_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(part in lowered for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    return value


def make_audit_event(
    *,
    run_id: str,
    site_id: str,
    action: BrowserAction,
    decision: ActionDecision,
) -> dict[str, Any]:
    action_value = "[REDACTED]" if action.sensitive else redact_value(action.selector, action.value)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "site_id": site_id,
        "action": {
            "kind": action.kind.value,
            "url": action.url,
            "selector": action.selector,
            "value": action_value,
            "sensitive": action.sensitive,
            "requires_confirmation": action.requires_confirmation,
        },
        "decision": {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "requires_confirmation": decision.requires_confirmation,
        },
    }
```

- [ ] **Step 4: Run audit tests and verify pass**

Run:

```powershell
python -m unittest tests.test_applai_audit -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add applai/audit.py tests/test_applai_audit.py
git commit -m "feat: add applai audit redaction"
```

Expected: commit succeeds.

## Task 5: Packaging And Optional Playwright Dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add package and optional dependency metadata**

Modify `pyproject.toml`.

Under `[project.optional-dependencies]`, add:

```toml
applai = [
    "playwright>=1.44.0",
]
```

Under `[tool.setuptools]`, keep the existing `py-modules` list and add:

```toml
packages = ["applai"]
```

- [ ] **Step 2: Verify metadata accepts the package**

Run:

```powershell
python -m pip install -e .
```

Expected: editable install succeeds and does not require Playwright because it is optional.

- [ ] **Step 3: Verify foundation tests still pass**

Run:

```powershell
python -m unittest tests.test_applai_models tests.test_applai_settings tests.test_applai_policy tests.test_applai_audit -v
```

Expected: all 20 tests pass.

- [ ] **Step 4: Commit**

Run:

```powershell
git add pyproject.toml
git commit -m "build: package applai optional browser dependency"
```

Expected: commit succeeds.

## Task 6: Browser Fixture Pages

**Files:**
- Create: `tests/fixtures/applai_site/index.html`
- Create: `tests/fixtures/applai_site/role.html`

- [ ] **Step 1: Create listing fixture**

Create `tests/fixtures/applai_site/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Example Careers</title>
  </head>
  <body>
    <main>
      <h1>Example Careers</h1>
      <a href="role.html">Senior AI Engineer</a>
      <button type="button">Filter roles</button>
      <input name="search" aria-label="Search roles">
    </main>
  </body>
</html>
```

- [ ] **Step 2: Create role fixture**

Create `tests/fixtures/applai_site/role.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Senior AI Engineer - Example Careers</title>
  </head>
  <body>
    <main>
      <h1>Senior AI Engineer</h1>
      <p>Build local AI automation tools with Python, Playwright, and Ollama.</p>
      <a href="https://careers.example.com/apply/123">Apply now</a>
      <button type="submit">Submit application</button>
      <input name="email" aria-label="Email address">
      <textarea name="cover_letter" aria-label="Cover letter"></textarea>
    </main>
  </body>
</html>
```

- [ ] **Step 3: Commit**

Run:

```powershell
git add tests/fixtures/applai_site/index.html tests/fixtures/applai_site/role.html
git commit -m "test: add applai browser fixtures"
```

Expected: commit succeeds.

## Task 7: Browser Worker

**Files:**
- Create: `applai/browser_worker.py`
- Test: `tests/test_applai_browser_worker.py`

- [ ] **Step 1: Write failing browser worker tests**

Create `tests/test_applai_browser_worker.py`:

```python
import shutil
import unittest
from pathlib import Path

from applai.browser_worker import BrowserWorker, PlaywrightUnavailableError
from applai.models import SiteConfig


def _playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return True


class ApplAIBrowserWorkerTests(unittest.TestCase):
    def _site(self) -> SiteConfig:
        return SiteConfig(
            id="local-fixture",
            name="Local Fixture",
            allowed_domains=("127.0.0.1", "localhost"),
            start_urls=("http://127.0.0.1/index.html",),
        )

    def test_blocks_unallowlisted_navigation_without_launching_browser(self):
        worker = BrowserWorker(self._site())

        with self.assertRaisesRegex(ValueError, "domain not allowlisted"):
            worker.validate_navigation("https://outside.example.com/role")

    @unittest.skipUnless(_playwright_available(), "Playwright is not installed")
    def test_extracts_observation_from_fixture_page(self):
        import http.server
        import socketserver
        import threading

        fixture_dir = Path("tests/fixtures/applai_site").resolve()
        screenshot_dir = Path("build_temp/test-applai-screenshots")
        self.addCleanup(lambda: shutil.rmtree(screenshot_dir, ignore_errors=True))

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(fixture_dir), **kwargs)

            def log_message(self, format, *args):
                return

        with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.shutdown)

            worker = BrowserWorker(
                self._site(),
                headless=True,
                slow_mo_ms=0,
                screenshot_dir=screenshot_dir,
            )
            try:
                observation = worker.open_and_observe(f"http://127.0.0.1:{port}/role.html")
            except PlaywrightUnavailableError:
                self.skipTest("Playwright browser runtime is not installed")
            finally:
                worker.close()

        self.assertEqual(observation.title, "Senior AI Engineer - Example Careers")
        self.assertIn("Build local AI automation", observation.visible_text)
        self.assertIn("https://careers.example.com/apply/123", observation.links)
        self.assertIn("Submit application", observation.buttons)
        self.assertIn("email", observation.inputs)
        self.assertTrue(Path(observation.screenshot_path).exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run browser worker tests and verify failure**

Run:

```powershell
python -m unittest tests.test_applai_browser_worker -v
```

Expected: fails with `ModuleNotFoundError: No module named 'applai.browser_worker'`.

- [ ] **Step 3: Implement browser worker**

Create `applai/browser_worker.py`:

```python
from __future__ import annotations

from pathlib import Path

from applai.models import ActionKind, BrowserAction, BrowserObservation, SiteConfig
from applai.policy import decide_action


class PlaywrightUnavailableError(RuntimeError):
    """Raised when Playwright or its browser runtime is not available."""


class BrowserWorker:
    def __init__(
        self,
        site: SiteConfig,
        *,
        headless: bool = False,
        slow_mo_ms: int = 50,
        screenshot_dir: Path | str = Path("logs") / "applai" / "screenshots",
    ) -> None:
        self.site = site
        self.headless = headless
        self.slow_mo_ms = slow_mo_ms
        self.screenshot_dir = Path(screenshot_dir)
        self._playwright = None
        self._browser = None
        self._page = None

    def validate_navigation(self, url: str) -> None:
        decision = decide_action(self.site, BrowserAction(kind=ActionKind.NAVIGATE, url=url))
        if not decision.allowed:
            raise ValueError(decision.reason)

    def open_and_observe(self, url: str) -> BrowserObservation:
        self.validate_navigation(url)
        page = self._ensure_page()
        page.goto(url, wait_until="domcontentloaded")
        return self.observe()

    def observe(self) -> BrowserObservation:
        page = self._ensure_page()
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = self.screenshot_dir / "latest.png"
        page.screenshot(path=str(screenshot_path), full_page=True)

        title = page.title()
        visible_text = page.locator("body").inner_text(timeout=3000)
        links = tuple(page.locator("a").evaluate_all("(els) => els.map((el) => el.href)"))
        buttons = tuple(
            text
            for text in page.locator("button, input[type=submit]").evaluate_all(
                "(els) => els.map((el) => el.innerText || el.value || el.getAttribute('aria-label') || '')"
            )
            if text
        )
        inputs = tuple(
            name
            for name in page.locator("input, textarea, select").evaluate_all(
                "(els) => els.map((el) => el.name || el.id || el.getAttribute('aria-label') || '')"
            )
            if name
        )

        return BrowserObservation(
            url=page.url,
            title=title,
            visible_text=visible_text,
            links=links,
            buttons=buttons,
            inputs=inputs,
            screenshot_path=str(screenshot_path),
        )

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._page = None

    def _ensure_page(self):
        if self._page is not None:
            return self._page

        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise PlaywrightUnavailableError("Playwright is not installed. Install with: pip install -e .[applai]") from exc

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo_ms,
            )
            self._page = self._browser.new_page()
            return self._page
        except PlaywrightError as exc:
            self.close()
            raise PlaywrightUnavailableError(
                "Playwright Chromium is not installed. Install it with: python -m playwright install chromium"
            ) from exc
```

- [ ] **Step 4: Run browser worker tests and verify pass or expected skip**

Run:

```powershell
python -m unittest tests.test_applai_browser_worker -v
```

Expected when Playwright is not installed: first test passes, fixture test is skipped.

Expected when Playwright and Chromium are installed: both tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add applai/browser_worker.py tests/test_applai_browser_worker.py
git commit -m "feat: add applai read-only browser worker"
```

Expected: commit succeeds.

## Task 8: Full Phase Verification

**Files:**
- Read: all files changed in this plan.

- [ ] **Step 1: Run foundation tests**

Run:

```powershell
python -m unittest tests.test_applai_models tests.test_applai_settings tests.test_applai_policy tests.test_applai_audit tests.test_applai_browser_worker -v
```

Expected when Playwright is not installed: all non-browser-runtime tests pass and the fixture browser test is skipped.

Expected when Playwright and Chromium are installed: all tests pass.

- [ ] **Step 2: Run existing screenshot/provider tests touched by concepts**

Run:

```powershell
python -m unittest tests.test_screenshot_batch tests.test_codex_provider -v
```

Expected: all existing tests pass.

- [ ] **Step 3: Inspect git diff**

Run:

```powershell
git diff --stat
git diff -- applai tests pyproject.toml
```

Expected: diff only contains applAI package files, applAI tests/fixtures, and the `pyproject.toml` package metadata change.

- [ ] **Step 4: Commit any final verification-only adjustments**

If a verification command exposed a mismatch in this plan, make the smallest correction to the implementation and tests, rerun the failing command, then commit:

```powershell
git add applai tests pyproject.toml
git commit -m "test: verify applai foundation browser slice"
```

Expected: commit succeeds only if verification required a correction. If no correction was needed, do not create an empty commit.

## Handoff To Phase 2

After this phase is implemented, the next plan should cover role extraction from DOM, metadata, and screenshots through local Ollama. It should use `BrowserObservation` as input and create a durable `RolePosting` model before adding form filling, credentials, Gmail, or live-site runs.

Do not start live-site automation until:

- `decide_action()` blocks off-allowlist navigation.
- Audit redaction tests pass.
- Browser worker tests pass or skip only because Playwright runtime is absent.
- User confirmation gates exist for submit, password entry, account registration, and email-token use.
