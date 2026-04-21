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
