"""
HelpAI — Internal QA & Training Overlay Tool

Entry point.  Registers global hotkeys, wires modules together,
and launches the overlay UI.
"""

import logging
import os
import sys
import threading

import keyboard  # global hotkey library

from analyzer import analyze_screenshot, analyze_text, analyze_transcript
from audio_capture import ContinuousCapture, check_audio_available
from config import (
    AUDIO_CAPTURE_ENABLED,
    AUDIO_SOURCE,
    HOTKEY_AUDIO_ANALYSIS,
    HOTKEY_QUICK_INPUT,
    HOTKEY_SCREENSHOT_FEEDBACK,
    HOTKEY_SHOW_CONVERSATION,
    SCREENSHOT_FEEDBACK_ENABLED,
)
from overlay import OverlayApp
from screenshot import capture_full_screen
from speech_to_text import describe_active_stt_provider, transcribe_audio_array

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("helpai")


# ── Global state ────────────────────────────────────────────────────────────
app: OverlayApp | None = None
capture: ContinuousCapture | None = None

# ── Conversation context ────────────────────────────────────────────────────
_last_request: str = ""           # last request text sent to AI
_last_response: str = ""          # last AI response


# ── Action handlers (run in background threads) ────────────────────────────

def _get_last_exchange() -> tuple[str, str] | None:
    """Return last (request, response) pair, or None if empty."""
    if _last_request and _last_response:
        return (_last_request, _last_response)
    return None

def _save_exchange(request_text: str, response_text: str) -> None:
    """Store last exchange for continuity (no extra API call)."""
    global _last_request, _last_response
    _last_request = request_text
    _last_response = response_text


def _action_audio_analysis() -> None:
    """Ctrl+D — use pre-transcribed text, send to LLM for analysis."""
    if not AUDIO_CAPTURE_ENABLED or capture is None:
        app.schedule(app.set_insight, "Audio capture is disabled in config.")
        return

    if not capture.is_running:
        app.schedule(app.set_insight, "Continuous capture is not running.")
        return

    app.schedule(app.show)

    # Check if user selected specific text in the panel
    selected = app.get_selection()
    if selected and selected.strip():
        loading_started = True
        app.schedule(app.begin_loading, "Analyzing Selection")
        app.schedule(app.set_status, "Analyzing selection…")
        app.schedule(
            app.set_insight,
            "Analyzing Selection\n\nReviewing the selected transcript and preparing a response."
        )
        try:
            result = analyze_text(
                selected.strip(),
                last_exchange=_get_last_exchange(),
            )
            _save_exchange(selected.strip(), result)
            app.schedule(app.set_insight, result)
        except Exception as exc:
            logger.exception("Selection analysis error")
            app.schedule(app.set_insight, f"Error: {exc}")
        finally:
            if loading_started:
                app.schedule(app.end_loading)
            app.schedule(app.set_status, "Listening…")
        return

    # Get accumulated transcript (already transcribed in background)
    input_text, output_text = capture.clear_transcript()

    if not input_text.strip() and not output_text.strip():
        app.schedule(app.set_status, "Listening…")
        app.schedule(app.set_insight, "No transcript yet — keep talking.")
        return

    loading_started = True
    app.schedule(app.begin_loading, "Analyzing Conversation")
    app.schedule(app.set_status, "Analyzing transcript…")
    app.schedule(
        app.set_insight,
        "Analyzing Conversation\n\nReading the latest transcript and drafting your response.",
    )

    try:
        result = analyze_transcript(
            input_text, output_text,
            last_exchange=_get_last_exchange(),
        )
        # Build combined request text for context extraction
        combined_req = ""
        if output_text.strip():
            combined_req += f"[OTHER PARTICIPANT]:\n{output_text.strip()}\n\n"
        if input_text.strip():
            combined_req += f"[YOU]:\n{input_text.strip()}"
        _save_exchange(combined_req, result)
        app.schedule(app.set_insight, result)
    except Exception as exc:
        logger.exception("Audio analysis error")
        app.schedule(app.set_insight, f"Error: {exc}")
    finally:
        if loading_started:
            app.schedule(app.end_loading)
        app.schedule(app.set_status, "Listening…")


def _action_screenshot_feedback() -> None:
    """Ctrl+E — capture screen, analyze with vision model, show insights."""
    if not SCREENSHOT_FEEDBACK_ENABLED:
        app.schedule(app.set_insight, "Screenshot feedback is disabled in config.")
        return

    app.schedule(app.set_status, "Capturing…")
    loading_started = False

    try:
        # Hide overlay synchronously so it's not in the screenshot
        hide_done = threading.Event()
        def _do_hide():
            app.hide()
            hide_done.set()
        app.schedule(_do_hide)
        hide_done.wait(timeout=1.0)
        import time
        time.sleep(0.15)  # extra frame for Windows to finish redraw

        png = capture_full_screen()

        show_done = threading.Event()
        def _do_show():
            app.show()
            show_done.set()
        app.schedule(_do_show)
        show_done.wait(timeout=1.0)

        loading_started = True
        app.schedule(app.begin_loading, "Analyzing Screen")
        app.schedule(app.set_status, "Analyzing…")
        app.schedule(
            app.set_insight,
            "Analyzing Screen\n\nInspecting the captured screen and extracting the relevant context."
        )

        result = analyze_screenshot(png)
        app.schedule(app.set_insight, result)
    except Exception as exc:
        logger.exception("Screenshot analysis error")
        app.schedule(app.show)
        app.schedule(app.set_insight, f"Error: {exc}")
    finally:
        if loading_started:
            app.schedule(app.end_loading)
        # Restore correct status based on capture state
        if capture and capture.is_running:
            app.schedule(app.set_status, "Listening…")
        else:
            app.schedule(app.set_status, "Ready")


def _action_quick_input_submit(text: str) -> None:
    """Handle text submitted from the quick-input dialog."""
    app.schedule(app.show)
    app.schedule(app.begin_loading, "Analyzing Request")
    app.schedule(app.set_status, "Analyzing…")
    app.schedule(
        app.set_insight,
        "Analyzing Request\n\nWorking through your prompt and preparing a response."
    )

    def run():
        try:
            result = analyze_text(
                text,
                last_exchange=_get_last_exchange(),
            )
            _save_exchange(text, result)
            app.schedule(app.set_insight, result)
        except Exception as exc:
            logger.exception("Quick-input analysis error")
            app.schedule(app.set_insight, f"Error: {exc}")
        finally:
            app.schedule(app.end_loading)
            app.schedule(app.set_status, "Ready")

    threading.Thread(target=run, daemon=True).start()


# ── Hotkey dispatchers (fire-and-forget threads) ────────────────────────────

def on_audio_hotkey() -> None:
    threading.Thread(target=_action_audio_analysis, daemon=True).start()


def on_screenshot_hotkey() -> None:
    threading.Thread(target=_action_screenshot_feedback, daemon=True).start()


def on_quick_input_hotkey() -> None:
    app.schedule(app.show)
    app.schedule(app.open_quick_input)


# ── Live transcript callback ────────────────────────────────────────────────

def _format_paragraphs(raw: str) -> str:
    """Format transcript lines into paragraphs using sentence endings."""
    segments = [segment.strip() for segment in raw.strip().split("\n") if segment.strip()]
    if not segments:
        return ""
    paragraphs: list[str] = []
    current_parts: list[str] = []
    for segment in segments:
        current_parts.append(segment)
        if segment.endswith((".", "!", "?", "…", ".\"", "!\"", "?\"", ".'", "!'", "?'")):
            paragraphs.append(" ".join(current_parts))
            current_parts = []
    if current_parts:
        paragraphs.append(" ".join(current_parts))
    return "\n\n".join(paragraphs)


def _on_transcript_update(input_text: str, output_text: str) -> None:
    """Called by ContinuousCapture when new transcript text is available."""
    lines = []
    if AUDIO_SOURCE in ("other", "both") and output_text.strip():
        lines.append(f"🔊 [THEM]:\n{_format_paragraphs(output_text)}")
    if AUDIO_SOURCE in ("me", "both") and input_text.strip():
        lines.append(f"🎙 [YOU]:\n{_format_paragraphs(input_text)}")
    if lines:
        app.schedule(app.set_conversation, "\n\n".join(lines))
        app.schedule(app.set_status, "Transcribing…")


# ── Stop / Quit ─────────────────────────────────────────────────────────────

def _clear_transcript() -> None:
    """Clear the accumulated transcript buffer in the capture object."""
    if capture:
        capture.clear_transcript()
        logger.info("Transcript cleared by user.")


def _stop_capture() -> None:
    """Stop continuous audio capture (bar Stop button)."""
    if capture and capture.is_running:
        capture.stop()
        logger.info("Capture stopped by user.")


def _quit_app() -> None:
    """Clean shutdown — ensure zero leftover processes."""
    logger.info("HelpAI shutting down…")

    # 1. Stop audio capture threads
    if capture and capture.is_running:
        capture.stop()

    # 2. Unhook all global hotkeys
    try:
        keyboard.unhook_all()
    except Exception:
        pass

    # 3. Destroy the tkinter root (closes all windows)
    try:
        if app and app.root:
            app.root.destroy()
    except Exception:
        pass

    logger.info("HelpAI stopped by user.")

    # 4. Force-terminate the process to kill any lingering daemon threads
    os._exit(0)


def _open_settings() -> None:
    """Toggle the integrated settings panel."""
    if app:
        app.toggle_settings()


# ── Bootstrap ───────────────────────────────────────────────────────────────

def main() -> None:
    global app, capture

    logger.info("Starting HelpAI…")
    logger.info("Speech-to-text provider: %s", describe_active_stt_provider())

    # Start continuous audio capture (mic + system loopback)
    if AUDIO_CAPTURE_ENABLED and check_audio_available():
        capture = ContinuousCapture(
            transcribe_fn=transcribe_audio_array,
            on_transcript=_on_transcript_update,
        )
        capture.start()
        audio_status = "Listening (mic + system audio)…"
    else:
        audio_status = "Audio capture unavailable"
        logger.warning("No audio input device — audio features disabled.")

    # Build overlay
    app = OverlayApp()
    app.on_quick_input_submit = _action_quick_input_submit
    app.on_audio = on_audio_hotkey
    app.on_screenshot = on_screenshot_hotkey
    app.on_stop = _stop_capture
    app.on_quit = _quit_app
    app.on_settings = _open_settings
    app.on_clear_conversation = _clear_transcript
    app.set_status(audio_status if capture else "Ready")

    # Register global hotkeys
    keyboard.add_hotkey(HOTKEY_AUDIO_ANALYSIS, on_audio_hotkey, suppress=False)
    keyboard.add_hotkey(HOTKEY_SCREENSHOT_FEEDBACK, on_screenshot_hotkey, suppress=False)
    keyboard.add_hotkey(HOTKEY_QUICK_INPUT, on_quick_input_hotkey, suppress=False)
    keyboard.add_hotkey(HOTKEY_SHOW_CONVERSATION, lambda: app.schedule(app.toggle_conversation), suppress=False)
    logger.info("Global hotkeys registered.")

    # Run the tkinter main loop (blocking)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        # If we get here without _quit_app (e.g. window closed via OS),
        # still clean up and force-exit.
        logger.info("HelpAI main loop ended — cleaning up.")
        if capture and capture.is_running:
            capture.stop()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        os._exit(0)
        sys.exit(0)


if __name__ == "__main__":
    main()
