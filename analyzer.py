"""
AI Analyzer module.

Wraps the OpenAI API for:
    • Text-based insight generation (GPT-4o)
    • Vision-based screenshot analysis (GPT-4o vision)
    • Speech-to-text via the configured transcription backend
"""

import base64
import logging

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL
from screenshot import prepare_vision_views
from speech_to_text import transcribe_wav_bytes

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

def transcribe_audio(wav_bytes: bytes) -> str:
    """Transcribe WAV audio using the configured speech-to-text backend."""
    transcript = transcribe_wav_bytes(wav_bytes)
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
    "- Sound like I'm talking to a colleague — natural pauses, casual connectors like "
    "'so basically', 'the thing is', 'what worked for me was'. NOT robotic or templated.\n"
    "- Vary sentence length. Mix short punchy takes with slightly longer explanations. "
    "Don't make every paragraph the same length or structure.\n"
    "- When I'd naturally hedge or show I'm thinking, reflect that: "
    "'I'd probably go with…', 'Off the top of my head…', 'honestly I think…'\n"
    "- End answers cleanly — wrap up the thought, don't trail off or add filler conclusions.\n"
    "- Use short paragraphs. Bold key terms with **word** for scannability.\n"
    "- When code is needed, provide clean, production-ready code.\n"
    "- Mention complexity, trade-offs, or edge cases when they matter, but don't force them.\n"
    "- Never say 'as an AI' or 'I'm an AI'. Never sound like I'm reciting a template. This IS my voice."
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
    "carefully — every line of code, every question, every error, every diagram, possible tests and test failures.\n\n"
    "You may receive multiple images of the same screen: the first is a full-screen overview, "
    "and the remaining images are zoomed crops in reading order. Use the overview for layout and "
    "global context, and use the crops whenever text or code is small.\n\n"
    "FIRST: Identify the programming language, framework, and technology stack visible "
    "on screen (e.g. Python/Django, JavaScript/React, TypeScript/Next.js, Java/Spring, "
    "C#/.NET, SQL, Terraform, Docker, etc.). Your response MUST use that exact language "
    "and framework — never answer in a different language than what's shown on screen.\n\n"
    "Write as ME — like I'm explaining to a colleague, not presenting a report:\n"
    "- If there's code or a coding problem: jump straight into my approach and provide "
    "a COMPLETE, working solution in the SAME language/framework shown on screen, "
    "with all imports and context. Never abbreviate.\n"
    "- If there's a question: lead with my actual take, then unpack the reasoning. "
    "Don't restate the question back.\n"
    "- If there's an error: name the root cause first, then my complete fix "
    "in the same language.\n"
    "- If there's a diagram or design: point out what I'd change with concrete improvements.\n\n"
    "Style:\n"
    "- Sound like a real person thinking through it — 'so the issue here is…', "
    "'the way I'd handle this…', 'honestly the cleanest approach is…'\n"
    "- Vary my delivery. Mix confident statements with natural hedges where appropriate.\n"
    "- End cleanly — land the thought, don't add a summary paragraph restating what I just said.\n"
    "- Give FULL, COMPLETE responses, Commented and Reasoned. Never say 'etc', '...' or skip content. "
    "If code is needed, write the entire working solution — every line, in the CORRECT "
    "language and framework.\n"
    "- Use **bold** for key terms. Short paragraphs. "
    "Never say 'as an AI'. Never sound scripted or templated."
)


def analyze_screenshot(image_bytes: bytes) -> str:
    """Send a screenshot to the vision model and return insights."""
    client = _get_client()
    views = prepare_vision_views(image_bytes)
    content: list[dict] = [{"type": "text", "text": VISION_PROMPT}]

    if len(views) > 1:
        content.append(
            {
                "type": "text",
                "text": (
                    "Image guide: image 1 is the full-screen overview. The remaining images are "
                    "native-resolution crops ordered left-to-right, top-to-bottom."
                ),
            }
        )

    for index, view in enumerate(views, start=1):
        detail = "high" if len(views) == 1 or index > 1 else "low"
        b64_image = base64.b64encode(view["bytes"]).decode("utf-8")
        content.append(
            {
                "type": "text",
                "text": f"View {index}: {view['label']} ({view['width']}x{view['height']}).",
            }
        )
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{view['mime_type']};base64,{b64_image}",
                    "detail": detail,
                },
            }
        )

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
        max_tokens=4096,
    )
    content = response.choices[0].message.content or ""
    logger.info("Screenshot analysis complete using %d view(s).", len(views))
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
