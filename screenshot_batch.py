"""Saved screenshot batch storage for deferred analysis."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class SavedScreenshot:
    index: int
    path: Path
    image_bytes: bytes


class ScreenshotBatch:
    """Collect screenshots in memory and mirror them to disk for debugging."""

    def __init__(self, base_dir: Path | str = Path("logs") / "screenshots"):
        self.base_dir = Path(base_dir)
        self._session_dir: Path | None = None
        self._items: list[SavedScreenshot] = []

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    def save(self, image_bytes: bytes) -> SavedScreenshot:
        if self._session_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self._session_dir = self.base_dir / timestamp
            self._session_dir.mkdir(parents=True, exist_ok=True)

        index = len(self._items) + 1
        extension = _image_extension(image_bytes)
        path = self._session_dir / f"screenshot-{index:03d}.{extension}"
        path.write_bytes(image_bytes)

        saved = SavedScreenshot(index=index, path=path, image_bytes=image_bytes)
        self._items.append(saved)
        return saved

    def image_bytes(self) -> list[bytes]:
        return [item.image_bytes for item in self._items]

    def describe(self) -> str:
        if not self._items:
            return "No saved screenshots."
        lines = [f"Saved screenshot batch ({len(self._items)} screenshot(s)):"]
        for item in self._items:
            lines.append(f"- Screenshot {item.index}: {item.path}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._items.clear()
        self._session_dir = None


def _image_extension(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "webp"
    return "img"
