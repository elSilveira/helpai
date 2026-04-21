"""
Screenshot module.

Captures the primary monitor (or a specific region) and returns the
image as PNG bytes suitable for vision-model analysis.
"""

import io
import logging

import mss
import mss.tools
from PIL import Image

logger = logging.getLogger(__name__)


def capture_full_screen() -> bytes:
    """Capture the entire primary monitor and return PNG bytes."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary monitor
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    logger.info("Screenshot captured (%dx%d).", img.width, img.height)
    return buf.getvalue()


def capture_region(left: int, top: int, width: int, height: int) -> bytes:
    """Capture a specific screen region and return PNG bytes."""
    region = {"left": left, "top": top, "width": width, "height": height}
    with mss.mss() as sct:
        raw = sct.grab(region)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
