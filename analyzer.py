"""
AI Analyzer module.

Wraps the OpenAI API for:
  • Audio transcription (Whisper)
  • Text-based insight generation (GPT-4o)
  • Vision-based screenshot analysis (GPT-4o vision)
"""

import base64
import io
import logging

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL, WHISPER_MODEL

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is not set. "
                "Please set it before running the application."
            )
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


# ── Audio → Text ────────────────────────────────────────────────────────────

# Known Whisper silence hallucinations (multi-language).
# These appear when Whisper receives near-silent audio.
_HALLUCINATION_EXACT: set[str] = {
    # English
    "thank you", "thank you.", "thanks.", "thanks",
    "thank you for watching", "thank you for watching.",
    "thanks for watching", "thanks for watching.",
    "like and subscribe", "please subscribe",
    "subscribe", "bye.", "bye", "you",
    # Japanese
    "ご視聴ありがとうございました", "ご視聴ありがとうございました。",
    # Chinese
    "谢谢观看", "谢谢观看。", "字幕由amara.org社区提供",
    "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目",
    # Korean
    "시청해주셔서 감사합니다", "시청해 주셔서 감사합니다",
    # Italian / Spanish / Portuguese / German / French
    "grazie", "grazie.", "grazie per la visione",
    "gracias", "gracias.", "gracias por ver",
    "obrigado", "obrigado.", "obrigada.",
    "danke", "danke.", "danke fürs zuschauen",
    "merci", "merci.", "merci d'avoir regardé",
    # Arabic
    "شكرا للمشاهدة",
    # Common filler
    "!", ".", "...", "…", "♪", "♪♪", "♪♪♪",
    "music", "[music]", "(music)",
}

_HALLUCINATION_PATTERNS: list[str] = [
    r'\bthanks? for watching\b',
    r'\bplease subscribe\b',
    r'\blike and subscribe\b',
    r'\bsubscribe\b',
    r'ご視聴ありがとうございました',
    r'谢谢观看',
    r'시청해\s*주셔서\s*감사합니다',
    r'\bgrazie\b',
    r'\bmerci\b',
    r'♪+',
    r'\[music\]',
    r'\(music\)',
]


def _filter_hallucinations(text: str) -> str:
    """Remove Whisper hallucination artifacts (repeated filler words on silence)."""
    import re

    # 1. Exact match — if the *entire* transcript is a known hallucination, drop it
    if text.strip().lower() in {h.lower() for h in _HALLUCINATION_EXACT}:
        return ""

    # 2. Collapse 3+ consecutive identical words ("you you you you" → "")
    text = re.sub(r'\b(\w+)(\s+\1){2,}\b', '', text, flags=re.IGNORECASE)

    # 3. Remove known hallucination phrases anywhere in the text
    for pat in _HALLUCINATION_PATTERNS:
        text = re.sub(pat, '', text, flags=re.IGNORECASE)

    # 4. Clean up extra whitespace
    text = re.sub(r'\s{2,}', ' ', text).strip()

    # 5. If what remains is ≤ 3 non-space characters, it's likely noise
    stripped = re.sub(r'[\s.,!?;:\-–—…]+', '', text)
    if len(stripped) <= 3:
        return ""

    return text


def transcribe_audio(wav_bytes: bytes) -> str:
    """Send WAV audio to Whisper and return the transcript."""
    client = _get_client()
    audio_file = io.BytesIO(wav_bytes)
    audio_file.name = "recording.wav"
    response = client.audio.transcriptions.create(
        model=WHISPER_MODEL,
        file=audio_file,
        response_format="text",
    )
    transcript = response.strip() if isinstance(response, str) else str(response)
    transcript = _filter_hallucinations(transcript)
    logger.info("Transcription complete (%d chars).", len(transcript))
    return transcript


# ── Text → Insights ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are ghostwriting MY personal response to what the OTHER PARTICIPANT just said. "
    "Focus on THEIR words — what they asked, what they said, what they need from me. "
    "Then write MY answer to THEM in first person.\n\n"
    "Rules:\n"
    "- The [OTHER PARTICIPANT] section is what matters most. That's who I'm responding to.\n"
    "- The [YOU] section (if present) is what I already said — use it for context only, don't repeat it.\n"
    "- Write as ME (first person). 'I would…', 'In my experience…', 'The way I see it…'\n"
    "- Get straight to the point. First sentence = my answer to their question/point.\n"
    "- Sound natural and conversational — like I'm talking to a colleague.\n"
    "- Use short paragraphs. Bold key terms with **word** for scannability.\n"
    "- When code is needed, provide clean, production-ready code.\n"
    "- Mention complexity, trade-offs, or edge cases naturally.\n"
    "- Never say 'as an AI' or 'I'm an AI'. This IS my voice."
)


def analyze_text(
    text: str,
    last_exchange: tuple[str, str] | None = None,
) -> str:
    """Generate insights from a text transcript or question.

    Args:
        text: The current transcript/question to analyze.
        last_exchange: Optional (request, response) from the previous analysis.
    """
    client = _get_client()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Inject previous exchange for continuity
    if last_exchange:
        prev_req, prev_resp = last_exchange
        if prev_req and prev_resp:
            messages.append({"role": "user", "content": prev_req[:2000]})
            messages.append({"role": "assistant", "content": prev_resp[:2000]})

    messages.append({"role": "user", "content": text})

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=4096,
    )
    content = response.choices[0].message.content or ""
    logger.info("Text analysis complete.")
    return content.strip()


# ── Screenshot → Insights ───────────────────────────────────────────────────

VISION_PROMPT = (
    "You are ghostwriting MY personal response to what's on this screen. "
    "Write in first person as if I am the one speaking. Read EVERYTHING on screen "
    "carefully — every line of code, every question, every error, every diagram.\n\n"
    "FIRST: Identify the programming language, framework, and technology stack visible "
    "on screen (e.g. Python/Django, JavaScript/React, TypeScript/Next.js, Java/Spring, "
    "C#/.NET, SQL, Terraform, Docker, etc.). Your response MUST use that exact language "
    "and framework — never answer in a different language than what's shown on screen.\n\n"
    "Write as ME:\n"
    "- If there's code or a coding problem: 'Here's how I'd solve this…' then provide "
    "a COMPLETE, working solution in the SAME language/framework shown on screen, "
    "with all imports and context. Never abbreviate.\n"
    "- If there's a question: 'So the way I think about this…' and answer with full depth.\n"
    "- If there's an error: 'The issue here is…' root cause first, then my complete fix "
    "in the same language.\n"
    "- If there's a diagram or design: 'What I'd change here is…' with concrete improvements.\n\n"
    "CRITICAL: Give FULL, COMPLETE responses. Never say 'etc', '...' or skip content. "
    "If code is needed, write the entire working solution — every line, in the CORRECT "
    "language and framework. "
    "Use **bold** for key terms. Short paragraphs. This is MY voice, MY answer. "
    "Never say 'as an AI'. Sound natural, confident, conversational."
)


def analyze_screenshot(png_bytes: bytes) -> str:
    """Send a screenshot to the vision model and return insights."""
    client = _get_client()
    b64_image = base64.b64encode(png_bytes).decode("utf-8")
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_image}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        max_tokens=4096,
    )
    content = response.choices[0].message.content or ""
    logger.info("Screenshot analysis complete.")
    return content.strip()


# ── Combined: Dual-stream Audio → Transcript → Insights ────────────────────

def analyze_transcript(
    input_text: str,
    output_text: str,
    last_exchange: tuple[str, str] | None = None,
) -> str:
    """Analyze pre-transcribed text from mic (input) and system (output) streams."""
    if not input_text.strip() and not output_text.strip():
        return "No speech detected in either stream."

    # Build transcript — prioritize OTHER PARTICIPANT
    combined = ""
    if output_text.strip():
        combined += f"[OTHER PARTICIPANT — what they said]:\n{output_text.strip()}\n\n"
    if input_text.strip():
        combined += f"[YOU — what I already said]:\n{input_text.strip()}\n\n"

    insights = analyze_text(combined, last_exchange=last_exchange)
    return (
        "━━ Transcript ━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + combined
        + "━━ My Response ━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + insights
    )


def analyze_dual_audio(
    input_wav: bytes | None,
    output_wav: bytes | None,
) -> str:
    """Transcribe mic (input) and system (output) audio separately,
    then generate insights that distinguish both speakers."""
    input_text = ""
    output_text = ""

    if input_wav:
        input_text = transcribe_audio(input_wav)
    if output_wav:
        output_text = transcribe_audio(output_wav)

    if not input_text and not output_text:
        return "No speech detected in either stream."

    combined = ""
    if output_text:
        combined += f"[OTHER PARTICIPANT — what they said]:\n{output_text}\n\n"
    if input_text:
        combined += f"[YOU — what I already said]:\n{input_text}\n\n"

    insights = analyze_text(combined)
    return (
        "━━ Transcript ━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + combined
        + "━━ My Response ━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + insights
    )


def analyze_audio(wav_bytes: bytes) -> str:
    """Legacy single-stream fallback."""
    transcript = transcribe_audio(wav_bytes)
    if not transcript:
        return "No speech detected in the recording."
    insights = analyze_text(transcript)
    return f"**Transcript:**\n{transcript}\n\n**Insights:**\n{insights}"
