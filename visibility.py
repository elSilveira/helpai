"""
Visibility control module.

Uses the Windows SetWindowDisplayAffinity API to exclude the overlay
from screen-capture and recording APIs.  This is the same mechanism
used by password managers and DRM players — a documented, first-party
Windows 10 2004+ capability.
"""

import ctypes
import ctypes.wintypes as wintypes
import logging

from config import WDA_EXCLUDEFROMCAPTURE

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32

# BOOL SetWindowDisplayAffinity(HWND hWnd, DWORD dwAffinity)
SetWindowDisplayAffinity = user32.SetWindowDisplayAffinity
SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
SetWindowDisplayAffinity.restype = wintypes.BOOL

# Extended window style constants
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080   # hides from taskbar & Alt-Tab
_WS_EX_APPWINDOW  = 0x00040000   # forces into taskbar (we remove this)


def exclude_from_capture(hwnd: int) -> bool:
    """Apply WDA_EXCLUDEFROMCAPTURE to *hwnd*.

    Returns True on success, False otherwise.
    """
    result = SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
    if result:
        logger.info("Window 0x%X excluded from capture.", hwnd)
    else:
        error = ctypes.get_last_error()
        logger.warning(
            "SetWindowDisplayAffinity failed for 0x%X (error %d).", hwnd, error
        )
    return bool(result)


def get_hwnd_from_tkinter(tk_root) -> int:
    """Retrieve the native Win32 HWND from a tkinter root/toplevel widget."""
    tk_root.update_idletasks()
    return int(tk_root.wm_frame(), 16)


def exclude_from_taskbar(hwnd: int) -> None:
    """Remove *hwnd* from the Windows taskbar and Alt-Tab switcher.

    Sets WS_EX_TOOLWINDOW and clears WS_EX_APPWINDOW so the window is
    invisible to shell even when it has focus.
    """
    try:
        GetWindowLongPtr = ctypes.windll.user32.GetWindowLongPtrW
        SetWindowLongPtr = ctypes.windll.user32.SetWindowLongPtrW
        GetWindowLongPtr.restype = ctypes.c_long
        SetWindowLongPtr.restype = ctypes.c_long
        exstyle = GetWindowLongPtr(hwnd, _GWL_EXSTYLE)
        new_style = (exstyle | _WS_EX_TOOLWINDOW) & ~_WS_EX_APPWINDOW
        SetWindowLongPtr(hwnd, _GWL_EXSTYLE, new_style)
    except Exception:
        logger.debug("exclude_from_taskbar failed for 0x%X", hwnd, exc_info=True)
