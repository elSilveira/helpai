# Coding Response Depth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add coding-only response-depth guidance to Suapper's analyzer prompts.

**Architecture:** Keep the behavior in `analyzer.py` as a shared prompt constant included by `_VOICE_RULES`, so typed coding requests and screenshot code reviews both inherit it. Preserve `AUTO_WHISPER_PROMPT` as-is.

**Tech Stack:** Python standard library, `unittest`, existing prompt string tests.

---

### Task 1: Add Prompt Regression Coverage

**Files:**
- Modify: `tests/test_analyzer_prompt.py`

- [ ] **Step 1: Write the failing test**

Add a test that asserts `SYSTEM_PROMPT` and `VISION_PROMPT` contain the coding-depth concepts: evidence, assumptions, contradictions, broad rule, risk, and verification.

- [ ] **Step 2: Run the focused test**

Run: `python -m unittest tests.test_analyzer_prompt.AnalyzerPromptTests.test_coding_prompts_require_deeper_evidence_and_verification_pass -v`

Expected: fail because the prompt does not yet include the new coding-depth wording.

### Task 2: Add Coding Depth Prompt Rules

**Files:**
- Modify: `analyzer.py`

- [ ] **Step 1: Add `_CODING_DEPTH_RULES`**

Add a compact prompt constant after `_get_active_profile()` or near `_VOICE_RULES`.

- [ ] **Step 2: Include it from `_VOICE_RULES`**

Append the constant after the existing coding problem rule so it only affects coding/code-review answers.

- [ ] **Step 3: Run focused tests**

Run: `python -m unittest tests.test_analyzer_prompt -v`

Expected: all prompt tests pass.
