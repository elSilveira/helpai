"""
Build script - creates a standalone HelpAI.exe using PyInstaller.

Usage:
    python build_exe.py

Output:
    dist/HelpAI/HelpAI.exe   (one-folder bundle, ready to distribute)
"""

import subprocess
import sys
from pathlib import Path

from helpai_version import __version__ as APP_VERSION

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build_temp"
ENTRY = ROOT / "launcher.py"

HIDDEN_IMPORTS = [
    "soundcard",
    "soundcard.mediafoundation",
    "numpy",
    "openai",
    "mss",
    "mss.windows",
    "PIL",
    "keyboard",
    "win32com",
    "win32com.client",
    "cffi",
    "pydantic",
    "httpx",
    "anyio",
    "anyio._backends",
    "anyio._backends._asyncio",
    "faster_whisper",
    "ctranslate2",
    "tokenizers",
    "onnxruntime",
    "huggingface_hub",
    "av",
]

DATA_FILES = [
    # (source, dest_folder_in_bundle)
]

# Check if icon exists
ICON = ROOT / "icon.ico"
ICON_ARG = str(ICON) if ICON.exists() else None


def ensure_pyinstaller():
    """Install PyInstaller if not present."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[*] Installing PyInstaller...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller", "-q"]
        )


def build():
    ensure_pyinstaller()
    version = APP_VERSION

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "HelpAI",
        "--onedir",
        "--noconsole",
        "--noconfirm",
        "--clean",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(ROOT),
    ]

    for imp in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", imp]

    for src, dest in DATA_FILES:
        cmd += ["--add-data", f"{src};{dest}"]

    if ICON_ARG:
        cmd += ["--icon", ICON_ARG]

    project_files = [
        "config.py", "settings.py", "settings_ui.py", "analyzer.py",
        "audio_capture.py", "screenshot.py", "overlay.py", "visibility.py",
        "main.py", "create_shortcut.py", "local_transcriber.py",
        "speech_to_text.py", "transcript_filters.py", "helpai.py",
        "helpai_version.py",
    ]
    for pf in project_files:
        p = ROOT / pf
        if p.exists():
            cmd += ["--add-data", f"{p};."]

    cmd.append(str(ENTRY))

    print(f"[*] Building HelpAI v{version} executable...")
    print(f"    Command: {' '.join(cmd[-5:])}")
    print()

    subprocess.check_call(cmd)

    exe = DIST / "HelpAI" / "HelpAI.exe"
    if exe.exists():
        print()
        print("=" * 50)
        print(f"  BUILD SUCCESSFUL  (v{version})")
        print(f"  Executable: {exe}")
        print(f"  Folder:     {DIST / 'HelpAI'}")
        print("=" * 50)
        print()
        print("  To distribute: zip the dist/HelpAI/ folder.")
        print("  Users just run HelpAI.exe - no Python needed.")
    else:
        print("[ERROR] Build failed - exe not found.")
        sys.exit(1)


if __name__ == "__main__":
    build()