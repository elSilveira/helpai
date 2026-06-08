import unittest

from persistent_context import (
    add_meeting_subject,
    build_persistent_context,
    disconsider_meeting_subject,
    remove_meeting_subject,
)


class PersistentContextTests(unittest.TestCase):
    def test_curriculum_context_is_included_when_saved(self):
        block = build_persistent_context(
            {
                "CURRICULUM_SOURCE": "resume.pdf",
                "CURRICULUM_TEXT": "Senior engineer with Python, AI, and platform experience.",
                "ACTIVE_MEETING_SUBJECT": "",
                "MEETING_SUBJECT_ENABLED": False,
            }
        )

        self.assertIn("Persistent user context", block)
        self.assertIn("Curriculum/background from resume.pdf", block)
        self.assertIn("Python, AI, and platform experience", block)
        self.assertIn("Use this only when relevant", block)

    def test_active_meeting_subject_is_included_only_when_enabled(self):
        settings = {
            "CURRICULUM_TEXT": "",
            "ACTIVE_MEETING_SUBJECT": "Senior backend interview about distributed systems.",
            "MEETING_SUBJECT_ENABLED": True,
        }

        self.assertIn("Current meeting/role subject", build_persistent_context(settings))

        settings["MEETING_SUBJECT_ENABLED"] = False

        self.assertNotIn("distributed systems", build_persistent_context(settings))

    def test_subjects_can_be_added_disconsidered_and_removed(self):
        settings = {"MEETING_SUBJECTS": [], "ACTIVE_MEETING_SUBJECT": "", "MEETING_SUBJECT_ENABLED": False}

        add_meeting_subject(settings, "Hiring manager screen")

        self.assertEqual(settings["MEETING_SUBJECTS"], ["Hiring manager screen"])
        self.assertEqual(settings["ACTIVE_MEETING_SUBJECT"], "Hiring manager screen")
        self.assertTrue(settings["MEETING_SUBJECT_ENABLED"])

        disconsider_meeting_subject(settings)

        self.assertEqual(settings["ACTIVE_MEETING_SUBJECT"], "Hiring manager screen")
        self.assertFalse(settings["MEETING_SUBJECT_ENABLED"])

        remove_meeting_subject(settings, "Hiring manager screen")

        self.assertEqual(settings["MEETING_SUBJECTS"], [])
        self.assertEqual(settings["ACTIVE_MEETING_SUBJECT"], "")
        self.assertFalse(settings["MEETING_SUBJECT_ENABLED"])


if __name__ == "__main__":
    unittest.main()
