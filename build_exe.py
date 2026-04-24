"""
Build script - creates a standalone HelpAI.exe using PyInstaller.

Usage:
    python build_exe.py

Output:
    dist/HelpAI/HelpAI.exe   (one-folder bundle, ready to distribute)
"""

import subprocess
import sys
import re
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
    "nvidia.cublas",
    "nvidia.cudnn",
    "nvidia.cuda_nvrtc",
    "pystray",
    "pystray._win32",
]

COLLECT_SUBMODULE_PACKAGES = [
    "faster_whisper",
]

COLLECT_DATA_PACKAGES = [
    "faster_whisper",
]

# Packages whose native binaries (.dll/.so) must be bundled.
# Without this, CUDA libs like cublas64_12.dll are missing at runtime.
COLLECT_BINARIES_PACKAGES = [
    "ctranslate2",
    "nvidia.cublas",
    "nvidia.cudnn",
    "nvidia.cuda_nvrtc",
    "onnxruntime",
]

REQUIRED_BUNDLE_PATHS = [
    Path("_internal") / "faster_whisper" / "assets" / "silero_vad_v6.onnx",
]

DATA_FILES = [
    # (source, dest_folder_in_bundle)
]

# Check if icon exists
ICON = ROOT / "icon.ico"
ICON_ARG = str(ICON) if ICON.exists() else None


def _windows_version_parts(version: str) -> tuple[int, int, int, int]:
    """Convert an app version string into a 4-part Windows version tuple."""
    parts = [int(part) for part in re.findall(r"\d+", version)[:4]]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def _write_version_file(version: str) -> Path:
    """Generate a PyInstaller version-info resource file for Windows builds."""
    BUILD.mkdir(parents=True, exist_ok=True)
    version_parts = _windows_version_parts(version)
    version_tuple = ", ".join(str(part) for part in version_parts)
    escaped_version = version.replace("'", "\\'")
    version_file = BUILD / "helpai_version_info.txt"
    content = (
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers=({version_tuple}),\n"
        f"    prodvers=({version_tuple}),\n"
        "    mask=0x3F,\n"
        "    flags=0x0,\n"
        "    OS=0x40004,\n"
        "    fileType=0x1,\n"
        "    subtype=0x0,\n"
        "    date=(0, 0)\n"
        "  ),\n"
        "  kids=[\n"
        "    StringFileInfo([\n"
        "      StringTable(\n"
        "        '040904B0',\n"
        "        [\n"
        "          StringStruct('CompanyName', 'HelpAI'),\n"
        "          StringStruct('FileDescription', 'HelpAI overlay assistant'),\n"
        f"          StringStruct('FileVersion', '{escaped_version}'),\n"
        "          StringStruct('InternalName', 'HelpAI'),\n"
        "          StringStruct('OriginalFilename', 'HelpAI.exe'),\n"
        "          StringStruct('ProductName', 'HelpAI'),\n"
        f"          StringStruct('ProductVersion', '{escaped_version}')\n"
        "        ]\n"
        "      )\n"
        "    ]),\n"
        "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n"
        "  ]\n"
        ")\n"
    )
    version_file.write_text(content, encoding="utf-8")
    return version_file


def ensure_pyinstaller():
    """Install PyInstaller if not present."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[*] Installing PyInstaller...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller", "-q"]
        )


def _verify_bundle(bundle_dir: Path) -> None:
    """Fail the build when required runtime assets were not bundled."""
    missing = [str(path) for path in REQUIRED_BUNDLE_PATHS if not (bundle_dir / path).exists()]
    if missing:
        print("[ERROR] Build incomplete - missing runtime files:")
        for path in missing:
            print(f"    {path}")
        sys.exit(1)


def build():
    ensure_pyinstaller()
    version = APP_VERSION
    version_file = _write_version_file(version)

    # Remove stale spec file to force PyInstaller to regenerate from CLI args
    stale_spec = ROOT / "HelpAI.spec"
    if stale_spec.exists():
        stale_spec.unlink()
        print("[*] Removed stale HelpAI.spec")

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

    for package in COLLECT_SUBMODULE_PACKAGES:
        cmd += ["--collect-submodules", package]

    for package in COLLECT_DATA_PACKAGES:
        cmd += ["--collect-data", package]

    for package in COLLECT_BINARIES_PACKAGES:
        cmd += ["--collect-binaries", package]

    for src, dest in DATA_FILES:
        cmd += ["--add-data", f"{src};{dest}"]

    if ICON_ARG:
        cmd += ["--icon", ICON_ARG]

    cmd += ["--version-file", str(version_file)]

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

    _verify_bundle(DIST / "HelpAI")

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