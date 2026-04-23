"""
Screenshot module.

Captures the primary monitor (or a specific region) and returns the
image as encoded bytes suitable for vision-model analysis.
"""

import ctypes
import io
import logging
import sys

import mss
import mss.tools
from PIL import Image

# ── DPI awareness ───────────────────────────────────────────────────────────
# Ensure screenshots capture at physical (native) resolution, not logical
# (DPI-scaled) resolution.  Must be set before any mss/GDI call.
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # Per-Monitor DPI Aware v2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()     # Fallback for older Windows
        except Exception:
            pass

logger = logging.getLogger(__name__)

_VISION_TILE_TRIGGER_WIDTH = 2200
_VISION_TILE_TRIGGER_HEIGHT = 1300
_VISION_WIDE_SCREEN_TRIGGER_WIDTH = 4200
_VISION_TALL_SCREEN_TRIGGER_HEIGHT = 2600
_VISION_MAX_VIEWS = 6
_VISION_TILE_OVERLAP_RATIO = 0.12
_VISION_OVERVIEW_WEBP_QUALITY = 84
_VISION_CROP_WEBP_QUALITY = 92


def _encode_png(image: Image.Image) -> bytes:
    """Encode an image as optimized lossless PNG bytes."""
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _encode_webp(image: Image.Image, quality: int, lossless: bool = False) -> bytes:
    """Encode an image as WebP bytes."""
    buf = io.BytesIO()
    save_kwargs = {"format": "WEBP", "method": 6}
    if lossless:
        save_kwargs["lossless"] = True
    else:
        save_kwargs["quality"] = quality
    image.save(buf, **save_kwargs)
    return buf.getvalue()


def _load_image_bytes(image_bytes: bytes) -> Image.Image:
    """Load encoded image bytes as an RGB PIL image."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        return image.convert("RGB")


def _encode_lossless_capture(image: Image.Image) -> tuple[bytes, str, str]:
    """Return the smallest lossless encoding for a captured screenshot."""
    png_bytes = _encode_png(image)
    best_bytes = png_bytes
    best_mime = "image/png"
    best_format = "PNG"

    try:
        webp_bytes = _encode_webp(image, quality=100, lossless=True)
        if len(webp_bytes) < len(best_bytes):
            best_bytes = webp_bytes
            best_mime = "image/webp"
            best_format = "WEBP"
    except Exception:
        logger.debug("Lossless WebP encoding unavailable; using PNG capture bytes.", exc_info=True)

    return best_bytes, best_mime, best_format


def _encode_vision_view(image: Image.Image, quality: int) -> tuple[bytes, str, str]:
    """Return the smallest practical upload encoding for a vision view."""
    png_bytes = _encode_png(image)
    best_bytes = png_bytes
    best_mime = "image/png"
    best_format = "PNG"

    try:
        webp_bytes = _encode_webp(image, quality=quality)
        if len(webp_bytes) < len(best_bytes):
            best_bytes = webp_bytes
            best_mime = "image/webp"
            best_format = "WEBP"
    except Exception:
        logger.debug("WebP encoding unavailable; using PNG vision bytes.", exc_info=True)

    return best_bytes, best_mime, best_format


def _limit_grid(cols: int, rows: int, max_tiles: int) -> tuple[int, int]:
    """Clamp a tile grid so it does not exceed the configured tile budget."""
    limited_cols = max(1, cols)
    limited_rows = max(1, rows)
    while limited_cols * limited_rows > max_tiles:
        if limited_cols >= limited_rows and limited_cols > 1:
            limited_cols -= 1
        elif limited_rows > 1:
            limited_rows -= 1
        else:
            break
    return limited_cols, limited_rows


def _choose_tile_grid(width: int, height: int) -> tuple[int, int]:
    """Choose a crop grid based on the screenshot size."""
    cols = 1 + int(width > _VISION_TILE_TRIGGER_WIDTH) + int(width > _VISION_WIDE_SCREEN_TRIGGER_WIDTH)
    rows = 1 + int(height > _VISION_TILE_TRIGGER_HEIGHT) + int(height > _VISION_TALL_SCREEN_TRIGGER_HEIGHT)
    return _limit_grid(cols, rows, _VISION_MAX_VIEWS)


def _axis_ranges(length: int, segments: int) -> list[tuple[int, int]]:
    """Split a dimension into overlapping ranges."""
    if segments <= 1:
        return [(0, length)]

    base = length / segments
    overlap = int(base * _VISION_TILE_OVERLAP_RATIO)
    ranges: list[tuple[int, int]] = []
    for index in range(segments):
        start = int(round(index * base))
        end = int(round((index + 1) * base))
        if index > 0:
            start = max(0, start - overlap)
        if index < segments - 1:
            end = min(length, end + overlap)
        ranges.append((start, end))
    return ranges


def prepare_vision_views(image_bytes: bytes) -> list[dict[str, object]]:
    """Build overview and crop views for high-resolution screenshot analysis."""
    image = _load_image_bytes(image_bytes)
    overview_bytes, overview_mime, overview_format = _encode_vision_view(
        image,
        quality=_VISION_OVERVIEW_WEBP_QUALITY,
    )
    views: list[dict[str, object]] = [
        {
            "label": "full-screen overview",
            "bytes": overview_bytes,
            "mime_type": overview_mime,
            "format": overview_format,
            "width": image.width,
            "height": image.height,
        }
    ]

    cols, rows = _choose_tile_grid(image.width, image.height)
    if cols == 1 and rows == 1:
        logger.info(
            "Prepared screenshot overview for vision (%dx%d, %.2f MB, %s).",
            image.width,
            image.height,
            len(overview_bytes) / (1024 * 1024),
            overview_format,
        )
        return views

    x_ranges = _axis_ranges(image.width, cols)
    y_ranges = _axis_ranges(image.height, rows)
    for row_index, (top, bottom) in enumerate(y_ranges, start=1):
        for col_index, (left, right) in enumerate(x_ranges, start=1):
            crop = image.crop((left, top, right, bottom))
            crop_bytes, crop_mime, crop_format = _encode_vision_view(
                crop,
                quality=_VISION_CROP_WEBP_QUALITY,
            )
            views.append(
                {
                    "label": f"zoom crop row {row_index} col {col_index}",
                    "bytes": crop_bytes,
                    "mime_type": crop_mime,
                    "format": crop_format,
                    "width": crop.width,
                    "height": crop.height,
                }
            )

    total_mb = sum(len(view["bytes"]) for view in views) / (1024 * 1024)
    logger.info(
        "Prepared screenshot views for vision (%dx%d, grid=%dx%d, views=%d, total=%.2f MB).",
        image.width,
        image.height,
        cols,
        rows,
        len(views),
        total_mb,
    )
    return views


def capture_full_screen() -> bytes:
    """Capture the entire primary monitor and return losslessly encoded bytes."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary monitor
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    image_bytes, mime_type, image_format = _encode_lossless_capture(img)
    logger.info(
        "Screenshot captured (%dx%d, %.2f MB, %s).",
        img.width,
        img.height,
        len(image_bytes) / (1024 * 1024),
        image_format,
    )
    return image_bytes


def capture_region(left: int, top: int, width: int, height: int) -> bytes:
    """Capture a specific screen region and return losslessly encoded bytes."""
    region = {"left": left, "top": top, "width": width, "height": height}
    with mss.mss() as sct:
        raw = sct.grab(region)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    image_bytes, _, _ = _encode_lossless_capture(img)
    return image_bytes
