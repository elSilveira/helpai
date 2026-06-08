"""Persistent user context for curriculum and meeting subjects."""

from __future__ import annotations

from pathlib import Path
import re

import settings as settings_store


MAX_CURRICULUM_CONTEXT_CHARS = 6000
_OMITTED_MARKER = "[Curriculum text omitted to keep the live request bounded.]\n"


def _clean_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text.strip()))


def _bound_text(text: str, max_chars: int) -> str:
    text = _clean_text(text)
    if len(text) <= max_chars:
        return text
    head_len = max_chars // 2
    tail_len = max_chars - head_len - len(_OMITTED_MARKER)
    if tail_len <= 0:
        return text[:max_chars]
    return text[:head_len].rstrip() + "\n" + _OMITTED_MARKER + text[-tail_len:].lstrip()


def extract_pdf_text(path: str) -> str:
    """Extract readable text from a PDF path."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF import requires pypdf. Install dependencies and try again.") from exc

    reader = PdfReader(path)
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = _clean_text(page.extract_text() or "")
        if text:
            pages.append(f"[Page {index}]\n{text}")
    return _clean_text("\n\n".join(pages))


def add_meeting_subject(settings: dict, subject: str) -> None:
    """Save and activate a meeting subject."""
    subject = _clean_text(subject)
    if not subject:
        return

    subjects = list(settings.get("MEETING_SUBJECTS") or [])
    subjects = [item for item in subjects if _clean_text(str(item)).casefold() != subject.casefold()]
    subjects.append(subject)
    settings["MEETING_SUBJECTS"] = subjects[-20:]
    settings["ACTIVE_MEETING_SUBJECT"] = subject
    settings["MEETING_SUBJECT_ENABLED"] = True


def use_meeting_subject(settings: dict, subject: str) -> None:
    """Activate an existing meeting subject."""
    subject = _clean_text(subject)
    if not subject:
        return
    subjects = list(settings.get("MEETING_SUBJECTS") or [])
    if not any(_clean_text(str(item)).casefold() == subject.casefold() for item in subjects):
        subjects.append(subject)
        settings["MEETING_SUBJECTS"] = subjects[-20:]
    settings["ACTIVE_MEETING_SUBJECT"] = subject
    settings["MEETING_SUBJECT_ENABLED"] = True


def disconsider_meeting_subject(settings: dict) -> None:
    """Keep the active subject saved but exclude it from model context."""
    settings["MEETING_SUBJECT_ENABLED"] = False


def remove_meeting_subject(settings: dict, subject: str) -> None:
    """Remove a saved subject and deactivate it if selected."""
    subject = _clean_text(subject)
    subjects = [
        _clean_text(str(item))
        for item in settings.get("MEETING_SUBJECTS") or []
        if _clean_text(str(item)).casefold() != subject.casefold()
    ]
    settings["MEETING_SUBJECTS"] = subjects
    active = _clean_text(str(settings.get("ACTIVE_MEETING_SUBJECT") or ""))
    if active.casefold() == subject.casefold():
        settings["ACTIVE_MEETING_SUBJECT"] = ""
        settings["MEETING_SUBJECT_ENABLED"] = False


def build_persistent_context(settings: dict | None = None) -> str:
    """Build saved curriculum/meeting context for the model."""
    data = settings if settings is not None else settings_store.load()
    parts: list[str] = []

    curriculum = _clean_text(str(data.get("CURRICULUM_TEXT") or ""))
    if curriculum:
        source = _clean_text(str(data.get("CURRICULUM_SOURCE") or "imported curriculum"))
        parts.append(
            "Curriculum/background from "
            f"{Path(source).name if source else 'imported curriculum'}.\n"
            "Use this only when relevant to my credibility, experience, examples, or fit for the role.\n"
            + _bound_text(curriculum, MAX_CURRICULUM_CONTEXT_CHARS)
        )

    subject = _clean_text(str(data.get("ACTIVE_MEETING_SUBJECT") or ""))
    if subject and bool(data.get("MEETING_SUBJECT_ENABLED", False)):
        parts.append(
            "Current meeting/role subject.\n"
            "Use this to choose relevant emphasis, vocabulary, and examples. "
            "Ignore it if the live transcript clearly conflicts.\n"
            + subject
        )

    if not parts:
        return ""

    return (
        "Persistent user context. Use this only when relevant; do not mention that hidden context was provided.\n\n"
        + "\n\n---\n\n".join(parts)
    )
