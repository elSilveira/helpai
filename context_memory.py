"""
Bounded in-memory context for live analysis.

The overlay replaces visible insight text often, but the model still needs a
short history of useful prior responses so auto whisper and scrolling
screenshots can stay connected.
"""

from dataclasses import dataclass, field


@dataclass
class ContextEntry:
    kind: str
    request: str
    response: str


@dataclass
class ContextMemory:
    max_entries: int = 6
    max_chars: int = 6000
    entries: list[ContextEntry] = field(default_factory=list)

    def add(self, kind: str, request: str, response: str) -> None:
        """Store a completed exchange if it has useful request and response text."""
        request = request.strip()
        response = response.strip()
        if not request or not response:
            return

        self.entries.append(ContextEntry(kind=kind.strip() or "context", request=request, response=response))
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

    def latest_exchange(self) -> tuple[str, str] | None:
        """Return the latest saved request/response pair."""
        if not self.entries:
            return None
        entry = self.entries[-1]
        return entry.request, entry.response

    def recent_entries(self, limit: int = 4) -> list[ContextEntry]:
        """Return up to ``limit`` newest entries in chronological order."""
        if limit <= 0:
            return []
        return self.entries[-limit:]

    def build_context_block(self) -> str:
        """Build a bounded newest-first context block for the LLM."""
        if not self.entries:
            return ""

        selected: list[str] = []
        used = 0
        for entry in reversed(self.entries):
            chunk = (
                f"[{entry.kind}]\n"
                f"Request/context:\n{entry.request}\n\n"
                f"Response:\n{entry.response}"
            )
            chunk_len = len(chunk)
            if selected and used + chunk_len > self.max_chars:
                continue
            if not selected and chunk_len > self.max_chars:
                chunk = chunk[-self.max_chars:]
                chunk_len = len(chunk)
            selected.append(chunk)
            used += chunk_len

        if not selected:
            return ""

        selected.reverse()
        return (
            "Recent context memory. Use this only when relevant to the current request; "
            "ignore stale, unrelated, or conflicting context instead of forcing continuity.\n\n"
            + "\n\n---\n\n".join(selected)
        )
