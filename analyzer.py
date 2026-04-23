"""
AI Analyzer module.

Wraps the OpenAI-compatible API for:
    • Text-based insight generation (GPT-4o / local Ollama models)
    • Vision-based screenshot analysis (GPT-4o vision / local Ollama models)
    • Speech-to-text via the configured transcription backend
"""

import base64
import logging
import re

from openai import OpenAI, NotFoundError, APIConnectionError

from config import (
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)
from screenshot import prepare_vision_views
from speech_to_text import transcribe_wav_bytes

logger = logging.getLogger(__name__)

_client: OpenAI | None = None
_active_provider: str | None = None


def _get_client() -> OpenAI:
    """Return an OpenAI-compatible client for the configured LLM provider."""
    global _client, _active_provider
    if _client is None or _active_provider != LLM_PROVIDER:
        _active_provider = LLM_PROVIDER
        if LLM_PROVIDER == "ollama":
            _client = OpenAI(
                base_url=f"{OLLAMA_BASE_URL}/v1",
                api_key="ollama",
                max_retries=0,  # fail fast — no confusing retry logs
            )
            logger.info("Using Ollama at %s with model %s", OLLAMA_BASE_URL, OLLAMA_MODEL)
        else:
            if not OPENAI_API_KEY:
                raise RuntimeError(
                    "OPENAI_API_KEY is not set. "
                    "Set it in Settings or switch LLM Provider to Ollama."
                )
            _client = OpenAI(api_key=OPENAI_API_KEY)
            logger.info("Using OpenAI API with model %s", OPENAI_MODEL)
    return _client


def _get_model() -> str:
    """Return the active model name based on provider."""
    return OLLAMA_MODEL if LLM_PROVIDER == "ollama" else OPENAI_MODEL


_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _strip_thinking(text: str) -> str:
    """Remove Qwen3/DeepSeek <think>…</think> blocks from output."""
    cleaned = _THINK_RE.sub("", text)
    # Handle unclosed <think> block (still generating thinking)
    if "<think>" in cleaned:
        cleaned = cleaned[:cleaned.index("<think>")]
    return cleaned.strip()


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
    "- Respond as if you know what you are talking about, not just random new questions.\n"
    "- Never say 'as an AI' or 'I'm an AI'. Never sound like I'm reciting a template. This IS my voice."
)


def analyze_text(
    text: str,
    last_exchange: tuple[str, str] | None = None,
    on_token: "callable | None" = None,
) -> str:
    """Generate insights from a text transcript or question.

    Args:
        text: The current transcript/question to analyze.
        last_exchange: Optional (request, response) from the previous analysis.
        on_token: If provided, called with accumulated text on each streamed chunk.
    """
    client = _get_client()
    is_ollama = LLM_PROVIDER == "ollama"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Inject previous exchange for continuity
    if last_exchange:
        prev_req, prev_resp = last_exchange
        if prev_req and prev_resp:
            messages.append({"role": "user", "content": prev_req[:2000]})
            messages.append({"role": "assistant", "content": prev_resp[:2000]})

    messages.append({"role": "user", "content": text})

    max_tok = 2048 if is_ollama else 4096
    use_stream = on_token is not None

    try:
        response = client.chat.completions.create(
            model=_get_model(),
            messages=messages,
            temperature=0.2,
            max_tokens=max_tok,
            stream=use_stream,
        )
    except NotFoundError:
        raise RuntimeError(
            f"Model '{OLLAMA_MODEL}' not found in Ollama.\n"
            f"Pull it first:  ollama pull {OLLAMA_MODEL}\n"
            "Or pick a different model in Settings \u2192 AI Model \u2192 Ollama."
        )
    except APIConnectionError as exc:
        if is_ollama:
            raise RuntimeError(
                "Cannot connect to Ollama. Make sure Ollama is running:\n"
                "  1. Install: irm https://ollama.com/install.ps1 | iex\n"
                f"  2. Pull model: ollama pull {OLLAMA_MODEL}\n"
                "  3. Start: ollama serve"
            ) from exc
        raise
    except Exception as exc:
        if is_ollama:
            raise RuntimeError(
                f"Ollama error: {exc}"
            ) from exc
        raise

    if use_stream:
        raw = ""
        for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                raw += delta
                cleaned = _strip_thinking(raw)
                if cleaned:
                    on_token(cleaned)
        content = _strip_thinking(raw)
    else:
        content = response.choices[0].message.content or ""
        content = _strip_thinking(content)

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


def analyze_screenshot(image_bytes: bytes, on_token: "callable | None" = None) -> str:
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

    is_ollama = LLM_PROVIDER == "ollama"
    max_tok = 2048 if is_ollama else 4096
    use_stream = on_token is not None

    try:
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {
                    "role": "user",
                    "content": content,
                }
            ],
            max_tokens=max_tok,
            stream=use_stream,
        )
    except NotFoundError:
        raise RuntimeError(
            f"Model '{OLLAMA_MODEL}' not found in Ollama.\n"
            f"Pull it first:  ollama pull {OLLAMA_MODEL}\n"
            "Or pick a different model in Settings \u2192 AI Model \u2192 Ollama."
        )
    except APIConnectionError as exc:
        if is_ollama:
            raise RuntimeError(
                "Cannot connect to Ollama. Make sure Ollama is running:\n"
                "  1. Install: irm https://ollama.com/install.ps1 | iex\n"
                f"  2. Pull model: ollama pull {OLLAMA_MODEL}\n"
                "  3. Start: ollama serve"
            ) from exc
        raise
    except Exception as exc:
        if is_ollama:
            raise RuntimeError(
                f"Ollama error: {exc}"
            ) from exc
        raise

    if use_stream:
        raw = ""
        for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                raw += delta
                cleaned = _strip_thinking(raw)
                if cleaned:
                    on_token(cleaned)
        content = _strip_thinking(raw)
    else:
        content = response.choices[0].message.content or ""
        content = _strip_thinking(content)

    logger.info("Screenshot analysis complete using %d view(s).", len(views))
    return content.strip()


# ── Combined: Dual-stream Audio → Transcript → Insights ────────────────────

def analyze_transcript(
    input_text: str,
    output_text: str,
    last_exchange: tuple[str, str] | None = None,
    on_token: "callable | None" = None,
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

    header = (
        "━━ Transcript ━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + combined
        + "━━ My Response ━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    # Wrap on_token to prepend the transcript header
    stream_cb = None
    if on_token is not None:
        def stream_cb(partial_text):
            on_token(header + partial_text)

    insights = analyze_text(combined, last_exchange=last_exchange, on_token=stream_cb)
    return header + insights


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
