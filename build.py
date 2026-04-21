"""
Build script — creates a standalone HelpAI.exe using PyInstaller.

Usage:
    python build.py

Output:
    dist/HelpAI/HelpAI.exe   (one-folder bundle, ready to distribute)
"""

import subprocess
import sys
from pathlib import Path

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


def read_app_version() -> str:
    """Read APP_VERSION from config.py without importing the module."""
    try:
        for line in (ROOT / "config.py").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("APP_VERSION"):
                return line.split('"')[1]
    except Exception:
        pass
    return "unknown"


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
    version = read_app_version()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "HelpAI",
        "--onedir",
        "--noconsole",                      # no terminal window
        "--noconfirm",                      # overwrite without asking
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

    # Collect all project .py files as data so settings/config are bundled
    project_files = [
        "config.py", "settings.py", "settings_ui.py", "analyzer.py",
        "audio_capture.py", "screenshot.py", "overlay.py", "visibility.py",
        "main.py", "create_shortcut.py", "local_transcriber.py",
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
        print("  Users just run HelpAI.exe — no Python needed.")
    else:
        print("[ERROR] Build failed — exe not found.")
        sys.exit(1)


if __name__ == "__main__":
    build()
