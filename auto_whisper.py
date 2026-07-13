"""
Auto-whisper helpers.

Keeps the decision logic separate from Tkinter/audio wiring so automatic
suggestions can be tested without opening devices or windows.
"""

from dataclasses import dataclass
import hashlib

from transcript_filters import format_transcript_paragraphs

AUTO_WHISPER_DEBOUNCE_SECONDS = 1.0


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


@dataclass
class AutoWhisperState:
    """Track which transcript paragraph state has already been analyzed."""

    last_fingerprint: str = ""

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
