# HelpAI — Internal QA & Training Overlay Tool

A lightweight Windows overlay application for internal quality-assurance
sessions, UX evaluations, and engineering training workflows.

## Features

| Feature | Hotkey | Description |
|---|---|---|
| Audio Analysis | `Ctrl+D` | Records microphone audio, transcribes via Whisper, generates QA insights |
| Screenshot Feedback | `Ctrl+E` | Captures screen, analyzes with GPT-4o vision, returns context-aware notes |
| Quick Input | `Ctrl+Shift+Enter` | Opens a text prompt for ad-hoc questions or note logging |

- **Capture-excluded overlay** — uses `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` so the overlay does not pollute screen recordings or broadcasts.
- **Semi-transparent, draggable** — always-on-top borderless window positioned in the top-right corner.
- **Configurable** — all settings in `config.py` using `SCREAMING_SNAKE_CASE`.

## Prerequisites

- Windows 10 version 2004 or later
- Python 3.11+
- An OpenAI API key with access to GPT-4o and Whisper

## Setup

```powershell
# Clone / navigate to the project
cd helpai

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Set your API key
$env:OPENAI_API_KEY = "sk-..."
```

## Running

```powershell
python main.py
```

The overlay window will appear in the top-right corner of your primary
monitor.  Use the hotkeys above to interact.

## Project Structure

```
helpai/
├── main.py            # Entry point — hotkey registration, action wiring
├── config.py          # All configuration constants
├── overlay.py         # Tkinter overlay UI (semi-transparent, draggable)
├── visibility.py      # Win32 SetWindowDisplayAffinity wrapper
├── audio_capture.py   # Microphone recording via sounddevice
├── screenshot.py      # Screen capture via mss + Pillow
├── analyzer.py        # OpenAI Whisper + GPT-4o integration
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

## Configuration

Edit `config.py` to change behaviour:

| Parameter | Default | Description |
|---|---|---|
| `AUDIO_CAPTURE_ENABLED` | `True` | Enable/disable audio recording |
| `SCREENSHOT_FEEDBACK_ENABLED` | `True` | Enable/disable screenshot analysis |
| `INSIGHT_OVERLAY_OPACITY` | `0.88` | Window transparency (0.0–1.0) |
| `AUDIO_CHUNK_DURATION` | `30` | Max recording length in seconds |
| `OPENAI_MODEL` | `gpt-4o` | Model for text/vision analysis |
| `HOTKEY_*` | see config | Keyboard shortcuts |

## Security & Privacy

- Audio data is processed in-memory and never written to disk.
- All API calls use HTTPS (OpenAI SDK default).
- The `OPENAI_API_KEY` is read from the environment, never hard-coded.
- The overlay window is excluded from capture to keep internal tools out of recordings.
