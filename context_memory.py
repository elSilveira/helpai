"""
Bounded in-memory context for live analysis.

The overlay replaces visible insight text often, but the model still needs a
short history of useful prior responses so auto whisper and scrolling
screenshots can stay connected.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from uuid import uuid4


@dataclass
class ContextEntry:
    kind: str
    request: str
    response: str


@dataclass
class VisibleFileContext:
    path: str
    snippets: list[str] = field(default_factory=list)
    last_seen_at: str = ""
    confidence: str = "medium"


@dataclass
class ScreenContextSnapshot:
    id: str
    order: int
    created_at: str
    extracted_text: str = ""
    visible_files: list[str] = field(default_factory=list)
    visible_editor_content: str = ""
    active_file: str | None = None
    inferred_requirements: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ScreenContextCumulative:
    challenge_summary: str = ""
    requirements: list[str] = field(default_factory=list)
    visible_project_structure: list[str] = field(default_factory=list)
    visible_files: dict[str, VisibleFileContext] = field(default_factory=dict)
    current_editor_file: str | None = None
    required_behavior: list[str] = field(default_factory=list)
    files_to_inspect: list[str] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    files_to_create: list[str] = field(default_factory=list)
    implementation_notes: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    final_file_checklist: list[str] = field(default_factory=list)


@dataclass
class ScreenContextSession:
    id: str
    created_at: str
    updated_at: str
    task_text: str = ""
    user_goal: str = ""
    screenshots: list[ScreenContextSnapshot] = field(default_factory=list)
    cumulative: ScreenContextCumulative = field(default_factory=ScreenContextCumulative)
    previous_outputs: dict[str, object] = field(default_factory=dict)


_NEW_TASK_RE = re.compile(
    r"\b(new|different|fresh)\s+(task|challenge|problem|screen|context)\b|\bstart over\b|\breset context\b",
    re.IGNORECASE,
)
_CONTINUE_TASK_RE = re.compile(
    r"\b(same|previous|continue|follow[- ]?up|after the last|next file|now|this)\b",
    re.IGNORECASE,
)
_PATH_RE = re.compile(
    r"(?:`([^`\n]+\.[A-Za-z0-9]+)`)|"
    r"\b([A-Za-z0-9_.\-\\/]+?\.(?:py|js|jsx|ts|tsx|json|ya?ml|toml|ini|env|css|scss|html|md|txt|java|cs|go|rs|rb|php|sql|sh|ps1|bat))\b"
)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_REQUIREMENT_HINT_RE = re.compile(
    r"\b(requirement|must|should|need|needs|implement|fix|update|create|preserve|include|ensure|behavior|test)\b",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_screen_context_session(task_text: str = "") -> ScreenContextSession:
    now = _now_iso()
    return ScreenContextSession(
        id=uuid4().hex,
        created_at=now,
        updated_at=now,
        task_text=task_text.strip(),
    )


def _clean_line(line: str, max_chars: int = 260) -> str:
    line = re.sub(r"\s+", " ", line.strip(" -*\t"))
    if len(line) > max_chars:
        return line[: max_chars - 1].rstrip() + "..."
    return line


def _merge_unique(target: list[str], values: list[str], limit: int | None = None) -> None:
    seen = {value.casefold() for value in target}
    for value in values:
        cleaned = _clean_line(value)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        target.append(cleaned)
        seen.add(key)
        if limit is not None and len(target) >= limit:
            del target[limit:]
            return


def _extract_paths(text: str) -> list[str]:
    paths: list[str] = []
    for match in _PATH_RE.finditer(text):
        path = (match.group(1) or match.group(2) or "").strip()
        path = path.strip(".,;:()[]{}").replace("\\", "/")
        if path:
            paths.append(path)
    return paths


def _extract_requirement_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _clean_line(raw_line)
        if line and _REQUIREMENT_HINT_RE.search(line):
            lines.append(line)
    return lines


def _extract_final_file_checklist(text: str) -> list[str]:
    match = re.search(r"(?im)^#{1,3}\s*Final File Checklist\s*$", text)
    if not match:
        return []

    checklist: list[str] = []
    for raw_line in text[match.end():].splitlines():
        if re.match(r"^#{1,3}\s+", raw_line):
            break
        line = _clean_line(raw_line)
        if line:
            checklist.append(line)
    return checklist


def _response_without_code(text: str) -> str:
    return _CODE_FENCE_RE.sub("", text).strip()


def should_continue_screen_context_session(input_text: str, current_session: ScreenContextSession | None) -> bool:
    """Return whether a screenshot should continue the active screen session."""
    if current_session is None:
        return False

    text = input_text.strip()
    if _NEW_TASK_RE.search(text):
        return False
    if _CONTINUE_TASK_RE.search(text):
        return True
    return True


@dataclass
class ContextMemory:
    max_entries: int = 6
    max_chars: int = 6000
    entries: list[ContextEntry] = field(default_factory=list)
    preserve_full_latest_kinds: frozenset[str] = frozenset({"screenshot"})
    screen_context: ScreenContextSession | None = None

    def add(self, kind: str, request: str, response: str) -> None:
        """Store a completed exchange if it has useful request and response text."""
        request = request.strip()
        response = response.strip()
        if not request or not response:
            return

        kind = kind.strip() or "context"
        if kind == "screenshot":
            started_new_screen_task = self._add_screenshot_to_screen_context(request, response)
            if started_new_screen_task:
                self.entries.clear()

        self.entries.append(ContextEntry(kind=kind, request=request, response=response))
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

    def clear(self) -> None:
        """Forget all saved exchanges so future analysis starts fresh."""
        self.entries.clear()
        self.screen_context = None

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
            preserve_full = not selected and entry.kind in self.preserve_full_latest_kinds
            if selected and used + chunk_len > self.max_chars:
                continue
            if not selected and chunk_len > self.max_chars and not preserve_full:
                chunk = chunk[-self.max_chars:]
                chunk_len = len(chunk)
            selected.append(chunk)
            used += chunk_len

        if not selected:
            return ""

        selected.reverse()
        parts: list[str] = []
        screen_block = self._build_screen_context_block()
        if screen_block:
            parts.append(screen_block)
        parts.append(
            "Recent context memory. Use this only when relevant to the current request; "
            "ignore stale, unrelated, or conflicting context instead of forcing continuity.\n\n"
            + "\n\n---\n\n".join(selected)
        )
        return "\n\n---\n\n".join(parts)

    def _add_screenshot_to_screen_context(self, request: str, response: str) -> bool:
        reset_recent_memory = False
        explicit_new_task = bool(_NEW_TASK_RE.search(request))
        if not should_continue_screen_context_session(request, self.screen_context):
            self.screen_context = _new_screen_context_session(request)
            reset_recent_memory = True
        elif self.screen_context is None:
            self.screen_context = _new_screen_context_session(request)
            reset_recent_memory = explicit_new_task

        session = self.screen_context
        assert session is not None

        now = _now_iso()
        visible_files = _extract_paths(request + "\n" + response)
        requirements = _extract_requirement_lines(response)
        checklist = _extract_final_file_checklist(response)
        snapshot = ScreenContextSnapshot(
            id=uuid4().hex,
            order=len(session.screenshots) + 1,
            created_at=now,
            extracted_text=_response_without_code(response),
            visible_files=visible_files,
            visible_editor_content=response,
            active_file=visible_files[0] if visible_files else None,
            inferred_requirements=requirements,
            notes=checklist,
        )
        session.screenshots.append(snapshot)
        session.updated_at = now

        cumulative = session.cumulative
        if not cumulative.challenge_summary:
            cumulative.challenge_summary = _clean_line(_response_without_code(response).splitlines()[0] if response else "")
        _merge_unique(cumulative.requirements, requirements, limit=40)
        _merge_unique(cumulative.required_behavior, requirements, limit=40)
        _merge_unique(cumulative.implementation_notes, [_response_without_code(response)[:900]], limit=20)
        _merge_unique(cumulative.final_file_checklist, checklist, limit=60)

        for path in visible_files:
            file_context = cumulative.visible_files.get(path)
            if file_context is None:
                file_context = VisibleFileContext(path=path, last_seen_at=now)
                cumulative.visible_files[path] = file_context
            file_context.last_seen_at = now
            _merge_unique(file_context.snippets, [_response_without_code(response)[:500]], limit=4)

            path_context = "\n".join(
                line for line in checklist + response.splitlines()
                if path.casefold() in line.casefold()
            ) or response
            lowered = path_context.casefold()
            if "create" in lowered or "add" in lowered:
                _merge_unique(cumulative.files_to_create, [path], limit=30)
            elif "update" in lowered or "edit" in lowered or "modify" in lowered or "fix" in lowered:
                _merge_unique(cumulative.files_to_modify, [path], limit=30)
            else:
                _merge_unique(cumulative.files_to_inspect, [path], limit=30)

        if visible_files:
            cumulative.current_editor_file = visible_files[0]

        code_blocks = _CODE_FENCE_RE.findall(response)
        session.previous_outputs = {
            "insight": _response_without_code(response)[:2000],
            "code": "\n\n".join(code_blocks)[-4000:],
            "fileChecklist": checklist,
        }
        return reset_recent_memory

    def _build_screen_context_block(self) -> str:
        session = self.screen_context
        if session is None:
            return ""

        cumulative = session.cumulative
        lines = [
            "Cumulative screen context session.",
            "The screenshots are incremental and may show different parts of the same task.",
            "Do not treat the latest screenshot as the full context.",
            f"Session id: {session.id}",
            f"Screenshots captured: {len(session.screenshots)}",
        ]
        if session.task_text:
            lines.append(f"Task text: {session.task_text}")
        if cumulative.challenge_summary:
            lines.append(f"Challenge summary: {cumulative.challenge_summary}")
        if cumulative.current_editor_file:
            lines.append(f"Current editor file: {cumulative.current_editor_file}")

        def add_section(title: str, values: list[str]) -> None:
            if not values:
                return
            lines.append("")
            lines.append(f"{title}:")
            for value in values:
                lines.append(f"- {value}")

        add_section("Merged requirements", cumulative.requirements)
        add_section("Required behavior", cumulative.required_behavior)
        add_section("Files to inspect", cumulative.files_to_inspect)
        add_section("Files to modify", cumulative.files_to_modify)
        add_section("Files to create", cumulative.files_to_create)
        add_section("Final file checklist so far", cumulative.final_file_checklist)

        if cumulative.visible_files:
            lines.append("")
            lines.append("Visible files seen across screenshots:")
            for path, file_context in cumulative.visible_files.items():
                lines.append(f"- {path} (last seen {file_context.last_seen_at})")

        lines.append("")
        lines.append("Screenshot snapshots:")
        for snapshot in session.screenshots:
            lines.append(f"- Snapshot {snapshot.order} at {snapshot.created_at}")
            if snapshot.visible_files:
                lines.append(f"  Visible files: {', '.join(snapshot.visible_files)}")
            if snapshot.inferred_requirements:
                lines.append(f"  Requirements: {'; '.join(snapshot.inferred_requirements[:5])}")
            excerpt = _clean_line(snapshot.extracted_text, max_chars=700)
            if excerpt:
                lines.append(f"  Extracted insight/text: {excerpt}")

        previous_insight = str(session.previous_outputs.get("insight") or "").strip()
        previous_code = str(session.previous_outputs.get("code") or "").strip()
        previous_checklist = session.previous_outputs.get("fileChecklist") or []
        if previous_insight or previous_code or previous_checklist:
            lines.append("")
            lines.append("Previous outputs from the latest screenshot response:")
            if previous_insight:
                lines.append(f"- insight: {_clean_line(previous_insight, max_chars=700)}")
            if previous_code:
                lines.append(f"- code: {_clean_line(previous_code, max_chars=700)}")
            if isinstance(previous_checklist, list) and previous_checklist:
                lines.append(f"- file checklist: {'; '.join(str(item) for item in previous_checklist)}")

        return "\n".join(lines)
