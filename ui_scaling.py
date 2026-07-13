"""DPI helpers for Tk windows that use fixed pixel geometry."""

from __future__ import annotations

import sys

BASE_DPI = 96.0
MIN_SCALE = 1.0
MAX_SCALE = 2.5


def calculate_scale(dpi: float | int) -> float:
    """Return a bounded UI scale for a Windows DPI value."""
    try:
        scale = float(dpi) / BASE_DPI
    except (TypeError, ValueError):
        scale = MIN_SCALE
    return max(MIN_SCALE, min(MAX_SCALE, round(scale, 2)))


def scale_px(value: int | float, scale: float) -> int:
    """Scale a pixel value while preserving zero."""
    scaled = int(round(float(value) * scale))
    if value and scaled == 0:
        return 1
    return scaled


def configure_process_dpi_awareness() -> None:
    """Opt into Windows DPI awareness before Tk creates windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        awareness_context = ctypes.c_void_p(-4)  # PER_MONITOR_AWARE_V2
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(awareness_context):
            return
    except Exception:
        pass
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
    except Exception:
        pass


def configure_tk_scaling(root) -> float:
    """Set Tk font scaling for *root* and return the pixel scale factor."""
    try:
        dpi = root.winfo_fpixels("1i")
    except Exception:
        dpi = BASE_DPI
    scale = calculate_scale(dpi)
    try:
        root.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        pass
    return scale
