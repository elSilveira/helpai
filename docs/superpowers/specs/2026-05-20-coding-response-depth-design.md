# Coding Response Depth Design

## Goal

Incorporate the response-depth lessons from `C:\Users\duzit\source\test\response_depth_lessons_for_whisper.md` only for coding and code-review answers.

## Context

`analyzer.py` owns the prompt text used for text, screenshot, and Codex-backed answers. `_VOICE_RULES` is shared by `SYSTEM_PROMPT` and `VISION_PROMPT`, so coding guidance placed there reaches typed coding requests and screenshot-based coding reviews. `AUTO_WHISPER_PROMPT` should stay lightweight and should not receive this deeper coding-review behavior.

## Design

Add a compact `_CODING_DEPTH_RULES` prompt block in `analyzer.py` and include it from `_VOICE_RULES` near the existing coding-specific rules.

The block should tell the model that for coding and code review it must:

- Separate direct evidence from assumptions.
- Treat tests, logs, runtime errors, screenshots, explicit user constraints, and actual code behavior as stronger evidence than guesses or prior answers.
- Resolve contradictions instead of forcing a clean answer too early.
- Prefer the broad rule that explains the failure over a one-off patch.
- Check risks around large, repeated, malformed, partial, stale, or changed inputs.
- State what was verified, what was not verified, or what check would prove the answer correct.

## Testing

Extend `tests/test_analyzer_prompt.py` with prompt assertions for the new coding-depth rule. The regression test should check both text and vision prompts because both can produce coding/code-review answers.

## Scope

This does not change token limits, provider selection, memory behavior, UI behavior, or general non-coding response profiles.
