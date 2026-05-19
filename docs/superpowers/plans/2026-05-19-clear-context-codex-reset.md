# Clear Context Codex Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Clear Context reset Suapper local context and the shared Codex app-server client when Codex is active.

**Architecture:** Keep the behavior centralized in `main._clear_context_memory()`, since both the UI action and shortcut already call that function. Use the existing `close_default_client()` helper from `codex_client.py`.

**Tech Stack:** Python, unittest, existing string-inspection tests.

---

### Task 1: Clear-Context Codex Reset

**Files:**
- Modify: `main.py`
- Modify: `tests/test_clear_context_shortcut.py`

- [ ] **Step 1: Write the failing test**

Add assertions to `tests/test_clear_context_shortcut.py`:

```python
def test_clear_context_resets_codex_client_when_codex_provider_is_active(self):
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "main.py").read_text(encoding="utf-8")

    self.assertIn("close_default_client()", main_source)
    self.assertIn("\"codex\" in (LLM_TEXT_PROVIDER, LLM_IMAGE_PROVIDER)", main_source)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_clear_context_shortcut -v`

Expected: the new test fails because `_clear_context_memory()` does not call `close_default_client()`.

- [ ] **Step 3: Implement minimal behavior**

Update `main._clear_context_memory()`:

```python
def _clear_context_memory() -> None:
    """Forget saved model context without clearing the visible transcript."""
    logger.info("Clearing saved context memory.")
    _context_memory.clear()
    if "codex" in (LLM_TEXT_PROVIDER, LLM_IMAGE_PROVIDER):
        try:
            close_default_client()
        except Exception:
            logger.debug("Failed to reset Codex client while clearing context.", exc_info=True)
```

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest tests.test_clear_context_shortcut tests.test_codex_client tests.test_context_memory -v`

Expected: all listed tests pass.
