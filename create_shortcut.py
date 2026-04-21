"""
Create a Windows desktop shortcut (.lnk) that launches HelpAI.

Uses the Windows Script Host COM object via win32com — works without
any extra DLLs.  Run once:  python create_shortcut.py
"""

import os
import sys
from pathlib import Path


def create_shortcut() -> str:
    """Create a .lnk on the user's Desktop. Returns the shortcut path."""
    try:
        import win32com.client
    except ImportError:
        # Fallback: use PowerShell to create the shortcut
        return _create_via_powershell()

    desktop = Path(os.environ.get("USERPROFILE", "~")) / "Desktop"
    shortcut_path = str(desktop / "HelpAI.lnk")

    project_dir = Path(__file__).resolve().parent
    target = sys.executable                       # pythonw.exe / python.exe
    arguments = f'"{project_dir / "launcher.py"}"'
    icon = str(project_dir / "icon.ico") if (project_dir / "icon.ico").exists() else ""

    shell = win32com.client.Dispatch("WScript.Shell")
    lnk = shell.CreateShortCut(shortcut_path)
    lnk.TargetPath = target
    lnk.Arguments = arguments
    lnk.WorkingDirectory = str(project_dir)
    lnk.Description = "HelpAI — Internal QA & Training Overlay"
    if icon:
        lnk.IconLocation = icon
    lnk.save()

    print(f"Shortcut created: {shortcut_path}")
    return shortcut_path


def _create_via_powershell() -> str:
    """Fallback: create .lnk using PowerShell COM interop."""
    import subprocess

    desktop = Path(os.environ.get("USERPROFILE", "~")) / "Desktop"
    shortcut_path = desktop / "HelpAI.lnk"
    project_dir = Path(__file__).resolve().parent
    target = sys.executable
    arguments = f'"{project_dir / "launcher.py"}"'

    ps_script = f'''
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("{shortcut_path}")
$lnk.TargetPath = "{target}"
$lnk.Arguments = '{arguments}'
$lnk.WorkingDirectory = "{project_dir}"
$lnk.Description = "HelpAI - Internal QA and Training Overlay"
$lnk.Save()
'''
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        check=True,
        capture_output=True,
    )
    print(f"Shortcut created: {shortcut_path}")
    return str(shortcut_path)


if __name__ == "__main__":
    create_shortcut()
