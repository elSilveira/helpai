import unittest
from pathlib import Path


class CurriculumMeetingSettingsTests(unittest.TestCase):
    def test_settings_define_curriculum_and_meeting_subject_defaults(self):
        root = Path(__file__).resolve().parents[1]
        settings_source = (root / "settings.py").read_text(encoding="utf-8")

        self.assertIn('"CURRICULUM_TEXT"', settings_source)
        self.assertIn('"CURRICULUM_SOURCE"', settings_source)
        self.assertIn('"MEETING_SUBJECTS"', settings_source)
        self.assertIn('"ACTIVE_MEETING_SUBJECT"', settings_source)
        self.assertIn('"MEETING_SUBJECT_ENABLED"', settings_source)

    def test_settings_ui_exposes_context_import_and_subject_controls(self):
        root = Path(__file__).resolve().parents[1]
        ui_source = (root / "settings_ui.py").read_text(encoding="utf-8")

        self.assertIn('("context"', ui_source)
        self.assertIn("Import PDF", ui_source)
        self.assertIn("Save / Use", ui_source)
        self.assertIn("Disconsider", ui_source)
        self.assertIn("Remove", ui_source)
        self.assertIn("CURRICULUM_TEXT", ui_source)
        self.assertIn("ACTIVE_MEETING_SUBJECT", ui_source)

    def test_main_prepends_persistent_context_to_recent_context(self):
        root = Path(__file__).resolve().parents[1]
        main_source = (root / "main.py").read_text(encoding="utf-8")

        self.assertIn("build_persistent_context", main_source)
        self.assertIn("memory_context = _context_memory.build_context_block()", main_source)


if __name__ == "__main__":
    unittest.main()
