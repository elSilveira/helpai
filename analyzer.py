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

import settings as _settings_store
from codex_client import get_default_client
from openai import OpenAI, NotFoundError, APIConnectionError

from config import (
    LLM_TEXT_PROVIDER,
    LLM_IMAGE_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_TEXT_MODEL,
    OPENAI_IMAGE_MODEL,
    CODEX_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_TEXT_MODEL,
    OLLAMA_IMAGE_MODEL,
)
from screenshot import prepare_vision_views
from speech_to_text import transcribe_wav_bytes

logger = logging.getLogger(__name__)

# Separate clients for text and image providers (they may differ)
_text_client: OpenAI | None = None
_image_client: OpenAI | None = None
_text_provider_cache: str | None = None
_image_provider_cache: str | None = None
_codex_client = None


def _make_client(provider: str) -> OpenAI:
    """Create an OpenAI-compatible client for the given provider."""
    if provider == "ollama":
        return OpenAI(
            base_url=f"{OLLAMA_BASE_URL}/v1",
            api_key="ollama",
            max_retries=0,
        )
    if provider == "codex":
        raise RuntimeError("Codex provider uses codex app-server, not an OpenAI-compatible client.")
    else:
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. "
                "Set it in Settings or switch provider to Ollama/Codex."
            )
        return OpenAI(api_key=OPENAI_API_KEY)


def _get_text_client() -> OpenAI:
    """Return the client for the text provider."""
    global _text_client, _text_provider_cache
    if _text_client is None or _text_provider_cache != LLM_TEXT_PROVIDER:
        _text_provider_cache = LLM_TEXT_PROVIDER
        _text_client = _make_client(LLM_TEXT_PROVIDER)
        model = OLLAMA_TEXT_MODEL if LLM_TEXT_PROVIDER == "ollama" else OPENAI_TEXT_MODEL
        logger.info("Text provider: %s (model=%s)", LLM_TEXT_PROVIDER, model)
    return _text_client


def _get_image_client() -> OpenAI:
    """Return the client for the image provider."""
    global _image_client, _image_provider_cache
    if _image_client is None or _image_provider_cache != LLM_IMAGE_PROVIDER:
        _image_provider_cache = LLM_IMAGE_PROVIDER
        _image_client = _make_client(LLM_IMAGE_PROVIDER)
        model = OLLAMA_IMAGE_MODEL if LLM_IMAGE_PROVIDER == "ollama" else OPENAI_IMAGE_MODEL
        logger.info("Image provider: %s (model=%s)", LLM_IMAGE_PROVIDER, model)
    return _image_client


def _get_codex_client():
    """Return the shared Codex app-server client."""
    global _codex_client
    if _codex_client is None:
        _codex_client = get_default_client()
    return _codex_client


def _get_model() -> str:
    """Return the active text model name based on provider."""
    if LLM_TEXT_PROVIDER == "codex":
        return CODEX_MODEL
    return OLLAMA_TEXT_MODEL if LLM_TEXT_PROVIDER == "ollama" else OPENAI_TEXT_MODEL


def _get_image_model() -> str:
    """Return the active image/vision model name based on provider."""
    if LLM_IMAGE_PROVIDER == "codex":
        return CODEX_MODEL
    return OLLAMA_IMAGE_MODEL if LLM_IMAGE_PROVIDER == "ollama" else OPENAI_IMAGE_MODEL


_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
_LAST_EXCHANGE_CONTEXT_CHARS = 4000
_AUTO_WHISPER_RECENT_CONTEXT_CHARS = 8000
_OMITTED_CONTEXT_MARKER = "[Earlier context omitted to keep the live whisper request bounded.]\n"


def _strip_thinking(text: str) -> str:
    """Remove Qwen3/DeepSeek <think>…</think> blocks from output."""
    cleaned = _THINK_RE.sub("", text)
    # Handle unclosed <think> block (still generating thinking)
    if "<think>" in cleaned:
        cleaned = cleaned[:cleaned.index("<think>")]
    return cleaned.strip()


def _keep_latest_context(text: str, max_chars: int) -> str:
    """Bound context while preserving the newest tail of the conversation."""
    text = text.strip()
    if len(text) <= max_chars:
        return text

    available = max_chars - len(_OMITTED_CONTEXT_MARKER)
    if available <= 0:
        return text[-max_chars:]
    return _OMITTED_CONTEXT_MARKER + text[-available:]


# ── Response Profiles ───────────────────────────────────────────────────────

RESPONSE_PROFILES = {
    "software_engineer": (
        "Profile: Senior Software Engineer\n"
        "- You think like a senior engineer: architecture, code quality, performance, and maintainability.\n"
        "- Lead with concrete technical details — specific APIs, design patterns, complexity analysis.\n"
        "- When code is involved, provide production-ready solutions with proper error handling.\n"
        "- Mention trade-offs, edge cases, and gotchas that matter in real systems.\n"
        "- Reference relevant tools, libraries, and best practices from the ecosystem."
    ),
    "tech_lead": (
        "Profile: Tech Lead\n"
        "- You think like a tech lead: balancing technical excellence with delivery, team dynamics, and business impact.\n"
        "- Frame technical decisions in terms of ROI, risk, and team velocity.\n"
        "- When discussing architecture, consider scalability, team skill set, and maintenance burden.\n"
        "- Provide clear recommendations with reasoning — not just options, but which option and why.\n"
        "- Address cross-team concerns: API contracts, deployment strategy, observability."
    ),
    "seller": (
        "Profile: Sales Professional\n"
        "- You think like a top sales professional: value-driven, persuasive, client-focused.\n"
        "- Frame everything in terms of business value, ROI, and competitive advantage.\n"
        "- Use clear, confident language that builds trust and urgency without being pushy.\n"
        "- Anticipate objections and address them proactively.\n"
        "- Focus on outcomes and benefits rather than features."
    ),
    "hr": (
        "Profile: HR Professional\n"
        "- You think like an experienced HR professional: people-first, policy-aware, empathetic but practical.\n"
        "- Frame discussions around employee experience, compliance, and organizational culture.\n"
        "- Reference relevant labor practices, conflict resolution strategies, and engagement frameworks.\n"
        "- Balance the needs of the individual with organizational goals.\n"
        "- Use inclusive, professional language that de-escalates and builds rapport."
    ),
    "trainer": (
        "Profile: Trainer & Coach\n"
        "- You think like a skilled trainer and coach: pedagogical, patient, structured.\n"
        "- Break complex topics into digestible steps with clear learning progression.\n"
        "- Use analogies, examples, and real-world scenarios to make concepts stick.\n"
        "- Encourage critical thinking — explain the 'why' behind every concept.\n"
        "- Provide actionable takeaways and practice suggestions."
    ),
}


def _get_active_profile() -> str:
    """Return the profile prompt for the currently selected profile (hot-reloaded)."""
    key = (_settings_store.get("RESPONSE_PROFILE") or "software_engineer").strip().lower()
    return RESPONSE_PROFILES.get(key, RESPONSE_PROFILES["software_engineer"])


def _messages_to_codex_prompt(messages: list[dict]) -> str:
    """Flatten chat-style messages into one Codex app-server text request."""
    parts = [
        "Respond only with the final assistant answer for HelpAI. "
        "Do not describe your process or mention the transport."
    ]
    for message in messages:
        role = str(message.get("role", "user")).upper()
        content = message.get("content", "")
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)


def _run_codex_text(messages: list[dict], on_token: "callable | None" = None) -> str:
    content = _get_codex_client().generate_text(
        _messages_to_codex_prompt(messages),
        on_token=on_token,
        model=CODEX_MODEL or None,
    )
    return _strip_thinking(content).strip()


# ── Audio → Text ────────────────────────────────────────────────────────────

def transcribe_audio(wav_bytes: bytes) -> str:
    """Transcribe WAV audio using the configured speech-to-text backend."""
    transcript = transcribe_wav_bytes(wav_bytes)
    logger.info("Transcription complete (%d chars).", len(transcript))
    return transcript


# ── Text → Insights ─────────────────────────────────────────────────────────

# ── Shared voice & style rules ──────────────────────────────────────────────

_VOICE_RULES = (
    "Voice & Style:\n"
    "- Write as ME in first person. Use wording I can say immediately.\n"
    "- Lead with the SUBSTANCE - facts, definitions, comparisons, technical detail. "
    "The first sentence must deliver concrete information, not acknowledge the question.\n"
    "- Use the current transcript, the last exchange, and visible context together. "
    "Continue the conversation instead of starting over.\n"
    "- Keep the default answer to 2 to 4 short paragraphs with natural pauses between ideas.\n"
    "- Each paragraph should add a new useful insight. Prefer what I should say next over background lectures.\n"
    "- Do not restate the transcript, summarize the meeting, or explain that context was provided.\n"
    "- Use bullets only when a list is materially easier to scan than short paragraphs.\n"
    "- When code is needed, explain the approach first, then provide the code, "
    "then explain why that approach is the right fit and only include gotchas that change the decision.\n"
    "- Correct factual errors clearly, but keep the correction compact.\n"
    "- End cleanly - land the thought without a recap or follow-up invitation.\n"
    "- Never say 'as an AI' or 'I'm an AI'. Never sound like a template. This IS my voice."
)

SYSTEM_PROMPT = (
    "You are ghostwriting MY response to the OTHER PARTICIPANT. "
    "Your job is to give me the next useful thing to say, not a long report. "
    "Focus on THEIR words - what they asked, claimed, paused on, or got wrong - and write MY answer in first person.\n\n"
    "Context rules:\n"
    "- The [OTHER PARTICIPANT] section is what matters most. That's who I'm responding to.\n"
    "- The [YOU] section is what I already said. Use it for continuity, don't repeat it.\n"
    "- If a previous user/assistant message is present, treat it as the last exchange and continue from it.\n"
    "- If the other participant made a factual error (e.g. wrong version history, incorrect claim), "
    "correct it immediately and clearly.\n"
    "- If there is a question, answer it directly first, then add the reasoning that matters.\n"
    "- If there is an error mentioned, name the likely root cause first, then the practical fix.\n"
    "- If the transcript is fragmented, infer the strongest useful intent from the latest complete thought.\n"
    "- Never ask the user questions back like 'let me know if you need more details'.\n\n"
    + _VOICE_RULES
)

AUTO_WHISPER_PROMPT = (
    "You are producing an automatic whisper for me during a live conversation. "
    "Use the retained transcript, prior responses, and the last exchange together so context is not lost. "
    "Give only the next useful thing I could say.\n\n"
    "Rules:\n"
    "- Do not ask questions.\n"
    "- Never generate follow-up questions or prompts for the user.\n"
    "- Do not recap or summarize the transcript.\n"
    "- Return 1 to 3 short paragraphs, separated by blank lines.\n"
    "- If there is nothing useful to add yet, return one short sentence saying the current point is covered.\n"
    "- Keep it first person, direct, and ready to say out loud."
)

VISION_PROMPT = (
    "You are ghostwriting MY response to what's on this screen. "
    "Write in first person as if I am the one speaking. Read EVERYTHING on screen "
    "carefully — every line of code, every question, every error, every diagram, possible tests and test failures.\n\n"
    "You may receive multiple images of the same screen: the first is a full-screen overview, "
    "and the remaining images are zoomed crops in reading order. Use the overview for layout and "
    "global context, and use the crops whenever text or code is small.\n\n"
    "FIRST: Identify the programming language, framework, and technology stack visible "
    "on screen (e.g. Python/Django, JavaScript/React, TypeScript/Next.js, Java/Spring, "
    "C#/.NET, SQL, Terraform, Docker, etc.). Your response MUST use that exact language "
    "and framework — never answer in a different language than what's shown on screen.\n\n"
    "Context rules:\n"
    "- If there's code or a coding problem: FIRST explain my approach in bullet points, "
    "THEN provide a COMPLETE, working solution in the SAME language/framework shown on screen, "
    "with all imports and context, THEN explain why that solution fits the problem.\n"
    "- If there's a question: lead with the definitive answer as bullet points, "
    "then explain the reasoning. Never restate the question.\n"
    "- If there's an error: name the root cause first in bullets, then my complete fix "
    "in the same language.\n"
    "- If there's a diagram or design: point out what I'd change with concrete improvements.\n"
    "- NEVER ask the user questions back. Give the full answer upfront.\n\n"
    + _VOICE_RULES
)

def analyze_text(
    text: str,
    last_exchange: tuple[str, str] | None = None,
    recent_context: str | None = None,
    on_token: "callable | None" = None,
) -> str:
    """Generate insights from a text transcript or question.

    Args:
        text: The current transcript/question to analyze.
        last_exchange: Optional (request, response) from the previous analysis.
        recent_context: Optional bounded context memory across recent responses.
        on_token: If provided, called with accumulated text on each streamed chunk.
    """
    is_ollama = LLM_TEXT_PROVIDER == "ollama"

    # Build effective system prompt with the active response profile (hot-reloaded)
    effective_system = _get_active_profile() + "\n\n" + SYSTEM_PROMPT
    messages = [{"role": "system", "content": effective_system}]

    # Inject previous exchange for continuity
    if last_exchange:
        prev_req, prev_resp = last_exchange
        if prev_req and prev_resp:
            messages.append(
                {
                    "role": "user",
                    "content": _keep_latest_context(prev_req, _LAST_EXCHANGE_CONTEXT_CHARS),
                }
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": _keep_latest_context(prev_resp, _LAST_EXCHANGE_CONTEXT_CHARS),
                }
            )

    if recent_context:
        messages.append(
            {
                "role": "system",
                "content": _keep_latest_context(recent_context, _AUTO_WHISPER_RECENT_CONTEXT_CHARS),
            }
        )

    messages.append({"role": "user", "content": text})

    if LLM_TEXT_PROVIDER == "codex":
        content = _run_codex_text(messages, on_token=on_token)
        logger.info("Text analysis complete via Codex.")
        return content

    client = _get_text_client()
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
        model = _get_model()
        raise RuntimeError(
            f"Model '{model}' not found in Ollama.\n"
            f"Pull it first:  ollama pull {model}\n"
            "Or pick a different model in Settings \u2192 AI Model \u2192 Ollama."
        )
    except APIConnectionError as exc:
        if is_ollama:
            raise RuntimeError(
                "Cannot connect to Ollama. Make sure Ollama is running:\n"
                "  1. Install: irm https://ollama.com/install.ps1 | iex\n"
                f"  2. Pull model: ollama pull {_get_model()}\n"
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


def analyze_auto_whisper(
    text: str,
    last_exchange: tuple[str, str] | None = None,
    recent_context: str | None = None,
    on_token: "callable | None" = None,
) -> str:
    """Generate a compact automatic live-conversation suggestion."""
    is_ollama = LLM_TEXT_PROVIDER == "ollama"
    messages = [{"role": "system", "content": _get_active_profile() + "\n\n" + AUTO_WHISPER_PROMPT}]

    if last_exchange:
        prev_req, prev_resp = last_exchange
        if prev_req and prev_resp:
            messages.append(
                {
                    "role": "user",
                    "content": _keep_latest_context(prev_req, _LAST_EXCHANGE_CONTEXT_CHARS),
                }
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": _keep_latest_context(prev_resp, _LAST_EXCHANGE_CONTEXT_CHARS),
                }
            )

    if recent_context:
        messages.append(
            {
                "role": "system",
                "content": _keep_latest_context(recent_context, _AUTO_WHISPER_RECENT_CONTEXT_CHARS),
            }
        )

    messages.append({"role": "user", "content": text})

    if LLM_TEXT_PROVIDER == "codex":
        content = _run_codex_text(messages, on_token=on_token)
        logger.info("Auto whisper complete via Codex.")
        return content

    client = _get_text_client()
    max_tok = 768 if is_ollama else 1024
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
        model = _get_model()
        raise RuntimeError(
            f"Model '{model}' not found in Ollama.\n"
            f"Pull it first:  ollama pull {model}\n"
            "Or pick a different model in Settings -> AI Model -> Ollama."
        )
    except APIConnectionError as exc:
        if is_ollama:
            raise RuntimeError(
                "Cannot connect to Ollama. Make sure Ollama is running:\n"
                "  1. Install: irm https://ollama.com/install.ps1 | iex\n"
                f"  2. Pull model: ollama pull {_get_model()}\n"
                "  3. Start: ollama serve"
            ) from exc
        raise
    except Exception as exc:
        if is_ollama:
            raise RuntimeError(f"Ollama error: {exc}") from exc
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

    logger.info("Auto whisper complete.")
    return content.strip()


# ── Screenshot → Insights ───────────────────────────────────────────────────


def analyze_screenshot(
    image_bytes: bytes,
    on_token: "callable | None" = None,
    recent_context: str | None = None,
) -> str:
    """Send a screenshot to the vision model and return insights."""
    views = prepare_vision_views(image_bytes)
    content: list[dict] = [{"type": "text", "text": VISION_PROMPT}]
    if recent_context:
        content.append(
            {
                "type": "text",
                "text": (
                    "Previous screenshot/conversation context. Use it only if it is related "
                    "to the current screen; ignore it if the screen has moved to a different task.\n\n"
                    + recent_context[:6000]
                ),
            }
        )

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

    if LLM_IMAGE_PROVIDER == "codex":
        prompt_parts: list[str] = []
        image_urls: list[str] = []
        for item in content:
            if item.get("type") == "text":
                prompt_parts.append(item.get("text", ""))
            elif item.get("type") == "image_url":
                image_url = item.get("image_url", {}).get("url", "")
                if image_url:
                    image_urls.append(image_url)
        codex_content = _get_codex_client().generate_text(
            "\n\n".join(prompt_parts),
            image_urls=image_urls,
            on_token=on_token,
            model=CODEX_MODEL or None,
        )
        logger.info("Screenshot analysis complete via Codex using %d view(s).", len(views))
        return _strip_thinking(codex_content).strip()

    client = _get_image_client()
    is_ollama = LLM_IMAGE_PROVIDER == "ollama"
    max_tok = 2048 if is_ollama else 4096
    use_stream = on_token is not None

    try:
        response = client.chat.completions.create(
            model=_get_image_model(),
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
        model = _get_image_model()
        raise RuntimeError(
            f"Model '{model}' not found in Ollama.\n"
            f"Pull it first:  ollama pull {model}\n"
            "Or pick a different model in Settings \u2192 AI Model \u2192 Ollama."
        )
    except APIConnectionError as exc:
        if is_ollama:
            raise RuntimeError(
                "Cannot connect to Ollama. Make sure Ollama is running:\n"
                "  1. Install: irm https://ollama.com/install.ps1 | iex\n"
                f"  2. Pull model: ollama pull {_get_image_model()}\n"
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
    recent_context: str | None = None,
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

    insights = analyze_text(
        combined,
        last_exchange=last_exchange,
        recent_context=recent_context,
        on_token=stream_cb,
    )
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
