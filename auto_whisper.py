"""
Auto-whisper helpers.

Keeps the decision logic separate from Tkinter/audio wiring so automatic
suggestions can be tested without opening devices or windows.
"""

from dataclasses import dataclass
import hashlib
import time

from transcript_filters import format_transcript_paragraphs

AUTO_WHISPER_DEBOUNCE_SECONDS = 4.0
AUTO_WHISPER_IDLE_RETRY_SECONDS = 2.0
AUTO_WHISPER_COOLDOWN_SECONDS = 20.0
AUTO_WHISPER_MIN_NEW_CHARS = 120


def _format_section(label: str, text: str) -> str:
    formatted = format_transcript_paragraphs(text)
    if not formatted:
        return ""
    return f"[{label}]:\n{formatted}"


def build_auto_whisper_request(input_text: str, output_text: str) -> str:
    """Build the user message for a compact automatic whisper."""
    sections = []
    other = _format_section("OTHER PARTICIPANT - latest retained context", output_text)
    mine = _format_section("YOU - what I already said", input_text)
    if other:
        sections.append(other)
    if mine:
        sections.append(mine)

    transcript = "\n\n".join(sections).strip()
    return (
        "Auto Whisper task:\n"
        "Use the retained transcript below and the last exchange, if present, to produce "
        "a compact suggestion I can say next. Do not ask questions. Do not recap the transcript. "
        "Return 1 to 3 short paragraphs only.\n\n"
        f"{transcript}"
    ).strip()


def transcript_fingerprint(input_text: str, output_text: str) -> str:
    """Return a stable fingerprint for the visible transcript paragraphs."""
    request = build_auto_whisper_request(input_text, output_text)
    if not request or not ("[OTHER PARTICIPANT" in request or "[YOU" in request):
        return ""
    return hashlib.sha256(request.encode("utf-8")).hexdigest()


def _new_text_since(previous: str, current: str) -> str:
    previous = previous.strip()
    current = current.strip()
    if not current:
        return ""
    if previous and current.startswith(previous):
        return current[len(previous):].strip()
    return current


def _meaningful_length(input_text: str, output_text: str) -> int:
    joined = " ".join(part.strip() for part in (input_text, output_text) if part.strip())
    return len(" ".join(joined.split()))


@dataclass
class AutoWhisperState:
    """Track which transcript paragraph state has already been analyzed."""

    last_fingerprint: str = ""
    last_input_text: str = ""
    last_output_text: str = ""
    last_sent_at: float | None = None

    def snapshot_from_capture(self, capture) -> tuple[str, str]:
        """Read retained transcript without clearing audio context."""
        return capture.get_transcript()

    def mark_if_changed(self, input_text: str, output_text: str) -> bool:
        """Return True once for each new non-empty transcript fingerprint."""
        current = transcript_fingerprint(input_text, output_text)
        if not current or current == self.last_fingerprint:
            return False
        self.last_fingerprint = current
        return True

    def retry_after_seconds(self, now: float | None = None) -> float:
        """Return remaining cooldown time before another auto whisper may run."""
        if self.last_sent_at is None:
            return 0.0
        if now is None:
            now = time.monotonic()
        return max(0.0, AUTO_WHISPER_COOLDOWN_SECONDS - (now - self.last_sent_at))

    def build_request_if_ready(
        self,
        input_text: str,
        output_text: str,
        *,
        now: float | None = None,
    ) -> str | None:
        """Build a request only when enough stable, unsent transcript exists."""
        current = transcript_fingerprint(input_text, output_text)
        if not current or current == self.last_fingerprint:
            return None

        if now is None:
            now = time.monotonic()
        if self.retry_after_seconds(now) > 0:
            return None

        new_input = _new_text_since(self.last_input_text, input_text)
        new_output = _new_text_since(self.last_output_text, output_text)
        if _meaningful_length(new_input, new_output) < AUTO_WHISPER_MIN_NEW_CHARS:
            return None

        request = build_auto_whisper_request(new_input, new_output)
        if not request:
            return None

        self.last_fingerprint = current
        self.last_input_text = input_text.strip()
        self.last_output_text = output_text.strip()
        self.last_sent_at = now
        return request
