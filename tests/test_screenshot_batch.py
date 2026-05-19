import unittest
import shutil
from pathlib import Path
from uuid import uuid4

from screenshot_batch import ScreenshotBatch


class ScreenshotBatchTests(unittest.TestCase):
    def _workspace_tmp(self) -> Path:
        path = Path("build_temp") / f"test-screenshot-batch-{uuid4().hex}"
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_saves_screenshots_to_one_session_directory_and_keeps_bytes(self):
        batch = ScreenshotBatch(base_dir=self._workspace_tmp())

        first = batch.save(b"\x89PNG\r\n\x1a\nfirst")
        second = batch.save(b"RIFFxxxxWEBPsecond")

        self.assertEqual(batch.count, 2)
        self.assertEqual(batch.image_bytes(), [b"\x89PNG\r\n\x1a\nfirst", b"RIFFxxxxWEBPsecond"])
        self.assertEqual(first.path.parent, second.path.parent)
        self.assertEqual(first.path.name, "screenshot-001.png")
        self.assertEqual(second.path.name, "screenshot-002.webp")
        self.assertTrue(first.path.exists())
        self.assertTrue(second.path.exists())

    def test_clear_forgets_saved_session_without_deleting_files(self):
        batch = ScreenshotBatch(base_dir=self._workspace_tmp())
        saved = batch.save(b"raw bytes")

        batch.clear()

        self.assertEqual(batch.count, 0)
        self.assertEqual(batch.image_bytes(), [])
        self.assertTrue(saved.path.exists())


if __name__ == "__main__":
    unittest.main()
