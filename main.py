"""
HelpAI — Internal QA & Training Overlay Tool

Entry point.  Registers global hotkeys, wires modules together,
and launches the overlay UI.
"""

import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

import keyboard  # global hotkey library
import pystray
from PIL import Image, ImageDraw, ImageFont

from analyzer import analyze_auto_whisper, analyze_screenshot, analyze_text, analyze_transcript
from auto_whisper import (
    AUTO_WHISPER_DEBOUNCE_SECONDS,
    AUTO_WHISPER_IDLE_RETRY_SECONDS,
    AutoWhisperState,
)
from codex_client import close_default_client, warm_default_client
from context_memory import ContextMemory
from audio_capture import ContinuousCapture, check_audio_available
from config import (
    AUDIO_CAPTURE_ENABLED,
    AUDIO_SOURCE,
    HOTKEY_AUDIO_ANALYSIS,
    HOTKEY_CLEAR_CONTEXT,
    HOTKEY_QUICK_INPUT,
    HOTKEY_SCREENSHOT_FEEDBACK,
    HOTKEY_SHOW_CONVERSATION,
    KILL_OLLAMA_ON_EXIT,
    LLM_TEXT_PROVIDER,
    LLM_IMAGE_PROVIDER,
    LOCAL_WHISPER_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_TEXT_MODEL,
    OLLAMA_IMAGE_MODEL,
    SCREENSHOT_FEEDBACK_ENABLED,
)
from local_transcriber import is_model_cached, preload_model
from overlay import LoadingSplash, OverlayApp
from screenshot import capture_full_screen
from speech_to_text import describe_active_stt_provider, get_active_stt_provider, transcribe_audio_array
from transcript_filters import format_transcript_paragraphs
from visibility import exclude_from_taskbar

# ── Logging ─────────────────────────────────────────────────────────────────
_LOG_FILE = Path(sys.executable).resolve().parent / "helpai.log" if getattr(sys, "frozen", False) else None


def _build_log_handlers() -> list[logging.Handler]:
    """Write frozen-app logs to disk so packaged failures are inspectable."""
    if _LOG_FILE is not None:
        try:
            return [logging.FileHandler(_LOG_FILE, encoding="utf-8")]
        except Exception:
            pass
    return [logging.StreamHandler()]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=_build_log_handlers(),
    force=True,
)
logger = logging.getLogger("helpai")
_AUDIO_LEVEL_REFRESH_MS = 140


# ── Global state ────────────────────────────────────────────────────────────
app: OverlayApp | None = None
capture: ContinuousCapture | None = None
_tray_icon: "pystray.Icon | None" = None

# ── Conversation context ────────────────────────────────────────────────────
_context_memory = ContextMemory(max_entries=10, max_chars=12000)
_SCREENSHOT_CONTEXT_REQUEST = (
    "Screenshot feedback request. Retain this screenshot response as continuing screen context "
    "for later screenshots until the user explicitly chooses clear context. Use it to preserve "
    "file, folder, layer, and code-boundary decisions across scrolling and multi-file tasks."
)
_auto_whisper_enabled: bool = False
_auto_whisper_state = AutoWhisperState()
_auto_whisper_timer: threading.Timer | None = None
_auto_whisper_running: bool = False
_auto_whisper_lock = threading.Lock()


# ── System tray ─────────────────────────────────────────────────────────────

def _make_tray_image() -> Image.Image:
    """Generate a simple 64×64 tray icon using PIL."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Filled circle background
    draw.ellipse([4, 4, 60, 60], fill="#89b4fa")
    # "AI" text centred
    try:
        font = ImageFont.truetype("segoeui.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    text = "AI"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((64 - tw) // 2, (64 - th) // 2 - 2), text, fill="#1e1e2e", font=font)
    return img


def _tray_toggle(_icon=None, _item=None) -> None:
    """Show or hide the overlay from the tray menu / icon click."""
    if app:
        app.schedule(app.toggle)


def _tray_quit(_icon=None, _item=None) -> None:
    """Quit triggered from the tray icon."""
    if app:
        app.schedule(_quit_app)


def _start_tray() -> None:
    """Build the pystray icon and run it detached in its own thread."""
    global _tray_icon
    from config import APP_NAME
    menu = pystray.Menu(
        pystray.MenuItem("Show / Hide", _tray_toggle, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _tray_quit),
    )
    _tray_icon = pystray.Icon(APP_NAME, _make_tray_image(), APP_NAME, menu)
    _tray_icon.run_detached()


# ── Action handlers (run in background threads) ────────────────────────────

def _get_last_exchange() -> tuple[str, str] | None:
    """Return last (request, response) pair, or None if empty."""
    return _context_memory.latest_exchange()

def _get_recent_context() -> str:
    """Return bounded recent context for continuity across automatic analysis."""
    return _context_memory.build_context_block()


def _save_exchange(request_text: str, response_text: str, kind: str = "conversation") -> None:
    """Store a bounded exchange for continuity (no extra API call)."""
    _context_memory.add(kind, request_text, response_text)


def _clear_context_memory() -> None:
    """Forget prior analysis context so the next request starts fresh."""
    global _auto_whisper_state
    _context_memory.clear()
    _auto_whisper_state = AutoWhisperState()
    logger.info("Context memory cleared by user.")
    if app:
        app.set_status("Context cleared")


def _get_previous_response_history(current_response: str, limit: int = 3) -> list[str]:
    """Return newest prior response texts for the insight panel history."""
    current = current_response.strip()
    responses = [entry.response for entry in _context_memory.recent_entries(limit + 1)]
    if current and responses and responses[-1].strip() == current:
        responses = responses[:-1]

    history: list[str] = []
    for response in reversed(responses):
        text = response.strip()
        if not text or text == current:
            continue
        history.append(response)
        if len(history) >= limit:
            break
    return history


def _set_insight_with_history(response_text: str) -> None:
    if app:
        app.set_insight_history(response_text, _get_previous_response_history(response_text))


def _set_auto_whisper_enabled(enabled: bool) -> None:
    """Enable/disable automatic non-destructive conversation whispers."""
    global _auto_whisper_enabled, _auto_whisper_timer
    with _auto_whisper_lock:
        _auto_whisper_enabled = enabled
        if not enabled and _auto_whisper_timer is not None:
            _auto_whisper_timer.cancel()
            _auto_whisper_timer = None
    if app:
        app.schedule(app.set_status, "Auto Whisper ON" if enabled else "Auto Whisper OFF")


def _schedule_auto_whisper() -> None:
    """Debounce auto whispering until transcript paragraphs settle briefly."""
    _schedule_auto_whisper_after(AUTO_WHISPER_DEBOUNCE_SECONDS)


def _schedule_auto_whisper_after(delay_seconds: float) -> None:
    """Schedule or replace the pending auto-whisper timer."""
    global _auto_whisper_timer
    if capture is None:
        return
    with _auto_whisper_lock:
        if not _auto_whisper_enabled:
            return
        if _auto_whisper_timer is not None:
            _auto_whisper_timer.cancel()
        _auto_whisper_timer = threading.Timer(max(0.1, delay_seconds), _run_auto_whisper)
        _auto_whisper_timer.daemon = True
        _auto_whisper_timer.start()


def _capture_has_active_audio() -> bool:
    if capture is None:
        return False
    try:
        levels = capture.get_audio_levels()
    except Exception:
        logger.debug("Could not read audio levels for auto-whisper gating.", exc_info=True)
        return False
    return any(bool(stream.get("active")) for stream in levels.values())


def _run_auto_whisper() -> None:
    """Read retained transcript and generate a compact suggestion if it changed."""
    global _auto_whisper_timer, _auto_whisper_running
    if capture is None or app is None:
        return

    with _auto_whisper_lock:
        _auto_whisper_timer = None
        if not _auto_whisper_enabled or _auto_whisper_running:
            return

    if _capture_has_active_audio():
        _schedule_auto_whisper_after(AUTO_WHISPER_IDLE_RETRY_SECONDS)
        return

    wait_seconds = _auto_whisper_state.retry_after_seconds()
    if wait_seconds > 0:
        _schedule_auto_whisper_after(wait_seconds)
        return

    input_text, output_text = _auto_whisper_state.snapshot_from_capture(capture)
    request_text = _auto_whisper_state.build_request_if_ready(input_text, output_text)
    if not request_text:
        return

    with _auto_whisper_lock:
        if not _auto_whisper_enabled or _auto_whisper_running:
            return
        _auto_whisper_running = True

    loading_started = False
    try:
        loading_started = True
        app.schedule(app.begin_loading, "Auto Whisper")
        app.schedule(app.set_status, "Auto whispering...")
        result = analyze_auto_whisper(
            request_text,
            last_exchange=_get_last_exchange(),
            recent_context=_get_recent_context(),
            on_token=lambda t: app.schedule(app.set_insight, t),
        )
        _save_exchange(request_text, result, kind="auto_whisper")
        app.schedule(_set_insight_with_history, result)
    except Exception as exc:
        logger.exception("Auto whisper error")
        app.schedule(app.set_insight, f"Auto Whisper error: {exc}")
    finally:
        with _auto_whisper_lock:
            _auto_whisper_running = False
        if loading_started:
            app.schedule(app.end_loading)
        if _auto_whisper_enabled:
            app.schedule(app.set_status, "Auto Whisper ON")
        else:
            app.schedule(app.set_status, "Listening...")


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
                recent_context=_get_recent_context(),
                on_token=lambda t: app.schedule(app.set_insight, t),
            )
            _save_exchange(selected.strip(), result, kind="selection")
            app.schedule(_set_insight_with_history, result)
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
            recent_context=_get_recent_context(),
            on_token=lambda t: app.schedule(app.set_insight, t),
        )
        # Build combined request text for context extraction
        combined_req = ""
        if output_text.strip():
            combined_req += f"[OTHER PARTICIPANT]:\n{output_text.strip()}\n\n"
        if input_text.strip():
            combined_req += f"[YOU]:\n{input_text.strip()}"
        _save_exchange(combined_req, result, kind="audio")
        app.schedule(_set_insight_with_history, result)
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

        result = analyze_screenshot(
            png,
            recent_context=_get_recent_context(),
            on_token=lambda t: app.schedule(app.set_insight, t),
        )
        _save_exchange(_SCREENSHOT_CONTEXT_REQUEST, result, kind="screenshot")
        app.schedule(_set_insight_with_history, result)
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
                recent_context=_get_recent_context(),
                on_token=lambda t: app.schedule(app.set_insight, t),
            )
            _save_exchange(text, result, kind="quick_input")
            app.schedule(_set_insight_with_history, result)
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

_last_transcript_text: str = ""


def _format_paragraphs(raw: str) -> str:
    """Format transcript lines into flowing text, joining segments naturally."""
    return format_transcript_paragraphs(raw)


def _on_transcript_update(input_text: str, output_text: str) -> None:
    """Called by ContinuousCapture when new transcript text is available."""
    global _last_transcript_text
    if app is None:
        return
    lines = []
    if AUDIO_SOURCE in ("other", "both") and output_text.strip():
        lines.append(f"🔊 [THEM]:\n{_format_paragraphs(output_text)}")
    if AUDIO_SOURCE in ("me", "both") and input_text.strip():
        lines.append(f"🎙 [YOU]:\n{_format_paragraphs(input_text)}")
    if not lines:
        return
    new_text = "\n\n".join(lines)
    # Skip scheduling if the text hasn't actually changed.
    if new_text == _last_transcript_text:
        return
    _last_transcript_text = new_text
    app.schedule(app.set_conversation, new_text)
    app.schedule(app.set_status, "Transcribing…")
    _schedule_auto_whisper()


def _refresh_audio_levels() -> None:
    """Drive the conversation-panel audio meters from the current capture state."""
    if app is None:
        return

    levels = capture.get_audio_levels() if capture else {}
    app.set_audio_levels(levels)

    try:
        app.root.after(_AUDIO_LEVEL_REFRESH_MS, _refresh_audio_levels)
    except Exception:
        logger.debug("Audio meter refresh stopped.", exc_info=True)


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


def _cleanup_ollama() -> None:
    """Unload models from GPU and optionally kill the Ollama process."""
    _uses_ollama = "ollama" in (LLM_TEXT_PROVIDER, LLM_IMAGE_PROVIDER)
    if not _uses_ollama:
        return

    # Unload all loaded models from GPU by setting keep_alive to 0
    models_to_unload = []
    if LLM_TEXT_PROVIDER == "ollama":
        models_to_unload.append(OLLAMA_TEXT_MODEL)
    if LLM_IMAGE_PROVIDER == "ollama":
        models_to_unload.append(OLLAMA_IMAGE_MODEL)
    for model in dict.fromkeys(models_to_unload):
        try:
            import urllib.request
            req_data = json.dumps({"model": model, "keep_alive": 0}).encode()
            req = urllib.request.Request(
                f"{OLLAMA_BASE_URL}/api/generate",
                data=req_data,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            resp.close()
            logger.info("Unloaded model %s from GPU.", model)
        except Exception:
            logger.debug("Failed to unload model %s (non-fatal).", model)

    # Kill the Ollama process if the user opted in
    if KILL_OLLAMA_ON_EXIT:
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "ollama.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
            # Also kill the runner/server process
            subprocess.run(
                ["taskkill", "/F", "/IM", "ollama_llama_server.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=0x08000000,
            )
            logger.info("Ollama processes killed.")
        except Exception:
            logger.debug("Failed to kill Ollama process (non-fatal).")


def _quit_app() -> None:
    """Clean shutdown — show closing overlay while cleanup runs."""
    logger.info("HelpAI shutting down…")

    # Show a closing overlay so the user knows it's shutting down
    try:
        from overlay import ClosingSplash
        splash = ClosingSplash(app.root if app else None)
    except Exception:
        splash = None

    def _do_cleanup():
        # 1. Stop audio capture threads
        if capture and capture.is_running:
            capture.stop()

        # 2. Unhook all global hotkeys
        try:
            keyboard.unhook_all()
        except Exception:
            pass

        # 3. Stop system tray icon
        try:
            if _tray_icon:
                _tray_icon.stop()
        except Exception:
            pass

        # 4. Unload Ollama models from GPU / kill process
        _cleanup_ollama()

        # 5. Stop the shared Codex app-server process, if it was started.
        close_default_client()

        logger.info("HelpAI stopped by user.")

        # 6. Force-terminate the process to kill any lingering daemon threads
        os._exit(0)

    # Hide the main overlay immediately, run cleanup in background
    try:
        if app and app.root:
            app.hide()
    except Exception:
        pass

    threading.Thread(target=_do_cleanup, daemon=True).start()
    # If splash exists, run its brief mainloop (auto-closes on os._exit)
    if splash:
        try:
            splash.run()
        except Exception:
            pass


def _open_settings() -> None:
    """Toggle the integrated settings panel."""
    if app:
        app.toggle_settings()


# ── Bootstrap ───────────────────────────────────────────────────────────────

def main() -> None:
    global app, capture

    logger.info("Starting HelpAI…")
    if _LOG_FILE is not None:
        logger.info("Writing logs to %s", _LOG_FILE)
    logger.info("Speech-to-text provider: %s", describe_active_stt_provider())

    # ── Splash screen ────────────────────────────────────────────────────────
    splash = LoadingSplash()

    def _background_init() -> None:
        global capture
        import time

        # Auto-start Ollama server if any provider uses ollama
        _uses_ollama = "ollama" in (LLM_TEXT_PROVIDER, LLM_IMAGE_PROVIDER)
        if _uses_ollama:
            import shutil, subprocess, os, json
            import urllib.request
            CREATE_NO_WINDOW = 0x08000000
            ollama_dir = os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "Programs", "Ollama",
            )
            if os.path.isdir(ollama_dir):
                os.environ["PATH"] = (
                    ollama_dir + os.pathsep + os.environ.get("PATH", "")
                )

            if shutil.which("ollama"):
                # ── Ensure server is running ────────────────────────
                def _ollama_reachable():
                    try:
                        r = urllib.request.urlopen(
                            f"{OLLAMA_BASE_URL}/api/version", timeout=2)
                        r.close()
                        return True
                    except Exception:
                        return False

                if _ollama_reachable():
                    logger.info("Ollama is already running.")
                else:
                    splash.set_status("Starting Ollama server\u2026")
                    try:
                        subprocess.Popen(
                            ["ollama", "serve"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=CREATE_NO_WINDOW,
                        )
                        logger.info("Ollama serve launched.")
                    except Exception:
                        logger.debug("ollama serve spawn failed.")
                    # Wait up to 10s for the server to become reachable
                    for _ in range(20):
                        time.sleep(0.5)
                        if _ollama_reachable():
                            break

                if not _ollama_reachable():
                    logger.warning("Ollama server did not start.")
                else:
                    # ── Ensure models are pulled ─────────────────────
                    _models_needed = []
                    if LLM_TEXT_PROVIDER == "ollama":
                        _models_needed.append(OLLAMA_TEXT_MODEL)
                    if LLM_IMAGE_PROVIDER == "ollama":
                        _models_needed.append(OLLAMA_IMAGE_MODEL)
                    _ollama_models = list(dict.fromkeys(_models_needed))
                    for _m in _ollama_models:
                        splash.set_status(f"Checking Ollama model {_m}\u2026")
                        model_ready = False
                        try:
                            req = urllib.request.urlopen(
                                f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
                            data = json.loads(req.read())
                            req.close()
                            names = [m.get("name", "") for m in data.get("models", [])]
                            model_ready = any(
                                n == _m or n.startswith(_m + "-")
                                for n in names
                            )
                        except Exception:
                            logger.debug("Could not list Ollama models.")

                        if not model_ready:
                            splash.set_status(
                                f"Downloading model {_m}\u2026\n"
                                "(first run only \u2014 cached afterwards)"
                            )
                            logger.info("Pulling Ollama model %s", _m)
                            try:
                                subprocess.run(
                                    ["ollama", "pull", _m],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    timeout=3600,
                                    creationflags=CREATE_NO_WINDOW,
                                )
                                logger.info("Model %s pulled.", _m)
                            except Exception:
                                logger.exception("Failed to pull Ollama model.")
                        else:
                            logger.info("Ollama model %s is ready.", _m)

                    # Warm up: load configured ollama models into GPU memory
                    for _warmup_model in _ollama_models:
                        splash.set_status("Loading model into GPU\u2026")
                        try:
                            req_data = json.dumps({
                                "model": _warmup_model,
                                "keep_alive": "30m",
                            }).encode()
                            req = urllib.request.Request(
                                f"{OLLAMA_BASE_URL}/api/generate",
                                data=req_data,
                                headers={"Content-Type": "application/json"},
                            )
                            resp = urllib.request.urlopen(req, timeout=120)
                            resp.close()
                            logger.info("Model %s loaded into memory.", _warmup_model)
                        except Exception:
                            logger.debug("Model warmup request failed for %s (non-fatal).", _warmup_model)
            else:
                logger.warning("Ollama provider selected but ollama not found on PATH.")

        if LLM_TEXT_PROVIDER == "codex" or LLM_IMAGE_PROVIDER == "codex":
            splash.set_status("Starting Codex service...")
            try:
                warm_default_client()
                logger.info("Codex app-server warmed and ready.")
            except Exception:
                logger.exception("Codex app-server warmup failed.")

        # Start audio capture
        if AUDIO_CAPTURE_ENABLED and check_audio_available():
            splash.set_status("Starting audio capture…")
            capture = ContinuousCapture(
                transcribe_fn=transcribe_audio_array,
                on_transcript=_on_transcript_update,
            )
            capture.start()
        else:
            logger.warning("No audio input device — audio features disabled.")

        # Pre-warm local Whisper model
        if get_active_stt_provider() == "local":
            cached = is_model_cached()
            if cached:
                splash.set_status(f"Loading speech model ({LOCAL_WHISPER_MODEL})\u2026")
            else:
                splash.set_status(
                    f"Downloading speech model ({LOCAL_WHISPER_MODEL})\u2026\n"
                    "(first run only \u2014 cached afterwards)"
                )
            try:
                preload_model()
            except Exception:
                logger.exception("Model preload failed.")

        splash.set_status("Ready!")
        time.sleep(0.4)
        splash.close()

    threading.Thread(target=_background_init, daemon=True).start()
    splash.run()  # blocks until splash.close() destroys the window

    # ── Build overlay (after splash closed) ──────────────────────────────────
    audio_status = "Listening (mic + system audio)…" if capture else "Audio capture unavailable"

    app = OverlayApp()
    app.on_quick_input_submit = _action_quick_input_submit
    app.on_audio = on_audio_hotkey
    app.on_screenshot = on_screenshot_hotkey
    app.on_stop = _stop_capture
    app.on_quit = _quit_app
    app.on_settings = _open_settings
    app.on_clear_conversation = _clear_transcript
    app.on_clear_context = _clear_context_memory
    app.on_auto_whisper_toggle = _set_auto_whisper_enabled
    app.set_status(audio_status if capture else "Ready")
    app.root.after(0, _refresh_audio_levels)

    # Exclude root window from taskbar / Alt-Tab (must happen after window exists)
    def _apply_taskbar_exclusion():
        try:
            hwnd = int(app.root.wm_frame(), 16)
            exclude_from_taskbar(hwnd)
        except Exception:
            logger.debug("Could not apply taskbar exclusion.", exc_info=True)
    app.root.after(100, _apply_taskbar_exclusion)

    # Start system tray icon (runs in its own thread)
    _start_tray()

    # Register global hotkeys
    keyboard.add_hotkey(HOTKEY_AUDIO_ANALYSIS, on_audio_hotkey, suppress=False)
    keyboard.add_hotkey(HOTKEY_SCREENSHOT_FEEDBACK, on_screenshot_hotkey, suppress=False)
    keyboard.add_hotkey(HOTKEY_QUICK_INPUT, on_quick_input_hotkey, suppress=False)
    keyboard.add_hotkey(HOTKEY_SHOW_CONVERSATION, lambda: app.schedule(app.toggle_conversation), suppress=False)
    keyboard.add_hotkey(HOTKEY_CLEAR_CONTEXT, lambda: app.schedule(_clear_context_memory), suppress=False)
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
        try:
            if _tray_icon:
                _tray_icon.stop()
        except Exception:
            pass
        _cleanup_ollama()
        os._exit(0)
        sys.exit(0)


if __name__ == "__main__":
    main()
