# Clear Context Codex Reset Design

## Goal

When the user triggers Clear Context, Suapper should clear both its local context memory and any reusable Codex coding provider state so the next answer starts from a fresh context.

## Current Behavior

`main._clear_context_memory()` clears the in-memory `ContextMemory`, including recent exchanges and cumulative screenshot context. Codex requests already start a new Codex thread per generation, but the shared Codex app-server client remains alive for application reuse.

## Design

Extend `main._clear_context_memory()` to reset the shared Codex client by calling `close_default_client()` when either text or image provider is configured as `codex`. This keeps the current visible transcript behavior unchanged and keeps OAuth login intact because Codex owns credentials outside the app-server process.

The reset should be best-effort: local context must be cleared first, and a Codex shutdown failure should be logged without preventing the user from clearing context.

## Testing

Add a focused regression test that inspects `main.py` for the Codex reset call in the clear-context path and for the provider guard. Existing `context_memory` tests already cover local memory clearing.
