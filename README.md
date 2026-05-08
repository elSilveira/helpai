# HelpAI - Free Local AI Overlay For QA, Training, And Coding Help

HelpAI is a lightweight Windows overlay for internal quality-assurance sessions,
UX evaluations, engineering training, and coding help. It can run fully locally
with Ollama and local speech-to-text, so the app itself is free to use and does
not include telemetry, analytics, tracking, ads, or app-side data collection.

## At A Glance

- **Free app** - no subscription, license server, analytics, or built-in paid service.
- **Local-first** - use Ollama for text/vision and faster-whisper for speech-to-text.
- **No app telemetry** - HelpAI does not collect, sell, or train on your data.
- **Cloud optional** - OpenAI and xAI are only used if you configure their API keys/providers.
- **Code-friendly output** - explanations and code are shown in separate overlay panels.
- **Capture-safe overlay** - the HelpAI window is excluded from screenshots and recordings.

## Privacy And Cost

HelpAI itself is free software to run locally. If you choose local providers
(`Ollama` for AI and `local`/`auto` faster-whisper for speech-to-text), prompts,
screenshots, audio transcription, and generated responses stay on your machine.

If you configure cloud providers, the selected content required for that action
is sent to that provider over HTTPS:

- OpenAI mode sends prompt text and/or screenshots to OpenAI for analysis.
- xAI STT mode sends audio for speech-to-text.
- Provider usage may cost money according to your OpenAI or xAI account.

HelpAI does not add its own telemetry layer. Settings are stored locally, and
audio is processed in memory rather than saved by the app.

## Features

| Feature | Hotkey | Description |
|---|---|---|
| Audio Analysis | `Ctrl+Shift+D` | Uses microphone and/or system audio, transcribes with local faster-whisper or optional xAI STT, then generates QA insights |
| Screenshot Feedback | `Ctrl+Shift+E` | Captures the screen, analyzes it with Ollama or OpenAI vision, and returns context-aware notes |
| Quick Input | `Ctrl+Shift+Enter` | Opens a text prompt for ad-hoc questions or note logging |

- **Capture-excluded overlay** - uses `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` so the overlay does not pollute screen recordings or broadcasts.
- **Semi-transparent, draggable** - always-on-top borderless window positioned in the top-right corner.
- **Configurable** - settings can be changed in the app or through `settings.json`.

## Prerequisites

- Windows 10 version 2004 or later
- Python 3.11+
- For a free local setup: Ollama installed and running, plus local faster-whisper
- Optional: an OpenAI API key for cloud text and screenshot analysis
- Optional: an xAI API key for cloud speech-to-text

## Setup

```powershell
# Clone / navigate to the project
cd helpai

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Free local mode: install/pull models in Ollama, then select Ollama in Settings.
# Example:
ollama pull qwen2.5:7b

# Optional cloud mode: set your API key for OpenAI analysis
$env:OPENAI_API_KEY = "sk-..."

# Optional: enable xAI speech-to-text
$env:XAI_API_KEY = "xai-..."
```

## Running

```powershell
python launcher.py
```

The overlay window will appear on your primary monitor. Use the hotkeys above
to interact.

If you install the project as a Python package, launch it with:

```powershell
helpai
```

Speech-to-text selection defaults to `auto`: if `XAI_API_KEY` is present and
xAI is selected, HelpAI can use xAI STT; otherwise it falls back to the local
faster-whisper model.

## Build And Packaging

To build both the Windows executable bundle and a pip-installable package:

```powershell
.\build.bat
```

That produces:

- `dist\HelpAI\HelpAI.exe` for the existing Windows installer flow
- `dist\pip\helpai-<version>-py3-none-any.whl` for `pip install`
- `dist\pip\helpai-<version>.tar.gz` as the source distribution

If you only want the Windows executable from Python, run:

```powershell
python build_exe.py
```

You can install the built wheel locally with:

```powershell
python -m pip install --user .\dist\pip\helpai-<version>-py3-none-any.whl
```

For direct source installs during development:

```powershell
python -m pip install -e .
```

Installed copies store `settings.json` in `%APPDATA%\HelpAI`, while repo and
PyInstaller builds keep settings next to the project or executable.

## Project Structure

```text
helpai/
|-- main.py             # Entry point: hotkey registration, action wiring
|-- config.py           # Configuration loaded from settings/environment
|-- settings.py         # Local settings storage
|-- settings_ui.py      # Settings window
|-- overlay.py          # Tkinter overlay UI and separate insight/code panels
|-- visibility.py       # Win32 SetWindowDisplayAffinity wrapper
|-- audio_capture.py    # Continuous microphone + loopback capture via SoundCard
|-- screenshot.py       # Screen capture via mss + Pillow
|-- analyzer.py         # OpenAI/Ollama-compatible analysis
|-- speech_to_text.py   # STT backend selection: xAI or local faster-whisper
|-- requirements.txt    # Python dependencies
`-- README.md           # This file
```

## Configuration

Most options can be changed in the settings UI. Advanced users can also edit
`settings.json` or environment variables.

| Parameter | Description |
|---|---|
| `LLM_TEXT_PROVIDER` | `ollama` for local text analysis or `openai` for cloud analysis |
| `LLM_IMAGE_PROVIDER` | `ollama` for local screenshot analysis or `openai` for cloud vision |
| `OPENAI_API_KEY` | Optional key for OpenAI cloud analysis |
| `OLLAMA_BASE_URL` | Local Ollama server URL, usually `http://localhost:11434` |
| `STT_PROVIDER` | `auto`, `local`, or `xai` speech-to-text backend |
| `XAI_API_KEY` | Optional key for xAI cloud speech-to-text |
| `AUDIO_CAPTURE_ENABLED` | Enable/disable audio capture |
| `SCREENSHOT_FEEDBACK_ENABLED` | Enable/disable screenshot analysis |
| `INSIGHT_OVERLAY_OPACITY` | Window transparency from `0.0` to `1.0` |
| `TRANSCRIPTION_INTERVAL` | Seconds between rolling background transcriptions |
| `HOTKEY_*` | Keyboard shortcuts |

## Security & Privacy Details

- HelpAI has no built-in telemetry, analytics, tracking, ads, or license checks.
- Local Ollama/faster-whisper mode keeps processing on your machine.
- Cloud provider mode only sends the content needed for the action you trigger.
- Audio data is processed in memory and never written to disk by HelpAI.
- All provider API calls use HTTPS.
- API keys can be stored in local settings or read from environment variables.
- The `XAI_API_KEY` is optional and only used when the xAI STT backend is configured.
- The overlay window is excluded from capture to keep internal tools out of recordings.
