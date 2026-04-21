"""
Shared transcript cleanup utilities for local and remote speech-to-text backends.
"""

import re

# Known silence hallucinations that commonly appear in Whisper-like models.
_HALLUCINATION_EXACT: set[str] = {
    "thank you", "thank you.", "thanks.", "thanks",
    "thank you for watching", "thank you for watching.",
    "thanks for watching", "thanks for watching.",
    "like and subscribe", "please subscribe",
    "subscribe", "bye.", "bye", "you",
    "ご視聴ありがとうございました", "ご視聴ありがとうございました。",
    "谢谢观看", "谢谢观看。", "字幕由amara.org社区提供",
    "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目",
    "시청해주셔서 감사합니다", "시청해 주셔서 감사합니다",
    "grazie", "grazie.", "grazie per la visione",
    "gracias", "gracias.", "gracias por ver",
    "obrigado", "obrigado.", "obrigada.",
    "danke", "danke.", "danke fürs zuschauen",
    "merci", "merci.", "merci d'avoir regardé",
    "شكرا للمشاهدة",
    "!", ".", "...", "…", "♪", "♪♪", "♪♪♪",
    "music", "[music]", "(music)",
}
_HALLUCINATION_EXACT_LOWER = {value.lower() for value in _HALLUCINATION_EXACT}

_HALLUCINATION_PATTERNS: tuple[str, ...] = (
    r"\bthanks? for watching\b",
    r"\bplease subscribe\b",
    r"\blike and subscribe\b",
    r"\bsubscribe\b",
    r"ご視聴ありがとうございました",
    r"谢谢观看",
    r"시청해\s*주셔서\s*감사합니다",
    r"\bgrazie\b",
    r"\bmerci\b",
    r"♪+",
    r"\[music\]",
    r"\(music\)",
)

_TECHNICAL_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\btype script\b", "TypeScript"),
    (r"\bthat to extend\b", "TypeScript"),
    (r"\bjava script\b", "JavaScript"),
    (r"\bgraph q l\b", "GraphQL"),
    (r"\bgraph ql\b", "GraphQL"),
    (r"\bnode js\b", "Node.js"),
)


def normalize_transcript_text(text: str) -> str:
    """Normalize whitespace and common technical term splits."""
    normalized = text
    for pattern, replacement in _TECHNICAL_REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", normalized).strip()


def is_hallucination(text: str) -> bool:
    """Return True when a transcript is a known silence artifact."""
    candidate = text.strip()
    if not candidate:
        return True
    if candidate.lower() in _HALLUCINATION_EXACT_LOWER:
        return True
    if re.match(r"^(\w+)(\s+\1){2,}$", candidate, re.IGNORECASE):
        return True

    words = candidate.split()
    if len(words) >= 6:
        for phrase_len in range(2, min(8, len(words) // 2 + 1)):
            phrase = " ".join(words[:phrase_len]).lower()
            count = 0
            index = 0
            while index <= len(words) - phrase_len:
                chunk = " ".join(words[index:index + phrase_len]).lower()
                if chunk == phrase:
                    count += 1
                    index += phrase_len
                else:
                    break
            if count >= 3 and count * phrase_len >= len(words) * 0.6:
                return True

    stripped = re.sub(r"[\s.,!?;:\-–—…♪()\[\]]+", "", candidate)
    return len(stripped) <= 2


def filter_transcript_text(text: str) -> str:
    """Remove common silence artifacts and normalize the resulting text."""
    candidate = text.strip()
    if not candidate:
        return ""
    if candidate.lower() in _HALLUCINATION_EXACT_LOWER:
        return ""

    filtered = re.sub(r"\b(\w+)(\s+\1){2,}\b", "", candidate, flags=re.IGNORECASE)
    for pattern in _HALLUCINATION_PATTERNS:
        filtered = re.sub(pattern, "", filtered, flags=re.IGNORECASE)

    filtered = normalize_transcript_text(filtered)
    stripped = re.sub(r"[\s.,!?;:\-–—…♪()\[\]]+", "", filtered)
    if len(stripped) <= 3:
        return ""
    return filtered


def is_low_quality_segment(segment) -> bool:
    """Filter out low-confidence or suspiciously short local-model segments."""
    text = segment.text.strip()
    words = text.split()
    if len(words) <= 2 and segment.avg_logprob < -0.5:
        return True
    if segment.avg_logprob < -0.8:
        return True
    if segment.no_speech_prob > 0.5:
        return True
    duration = segment.end - segment.start
    if duration < 0.5 and len(words) <= 2:
        return True
    return False