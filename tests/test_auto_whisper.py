import unittest

import analyzer
from auto_whisper import AutoWhisperState, build_auto_whisper_request


class FakeCapture:
    def __init__(self, input_text="", output_text=""):
        self.input_text = input_text
        self.output_text = output_text
        self.get_calls = 0
        self.clear_calls = 0

    def get_transcript(self):
        self.get_calls += 1
        return self.input_text, self.output_text

    def clear_transcript(self):
        self.clear_calls += 1
        return self.input_text, self.output_text


class AutoWhisperTests(unittest.TestCase):
    def test_reads_transcript_without_clearing_context(self):
        capture = FakeCapture(output_text="First paragraph.\nSecond paragraph.")
        state = AutoWhisperState()

        snapshot = state.snapshot_from_capture(capture)

        self.assertEqual(snapshot, ("", "First paragraph.\nSecond paragraph."))
        self.assertEqual(capture.get_calls, 1)
        self.assertEqual(capture.clear_calls, 0)

    def test_only_new_paragraph_fingerprint_should_trigger(self):
        state = AutoWhisperState()

        self.assertTrue(state.mark_if_changed("", "First paragraph."))
        self.assertFalse(state.mark_if_changed("", "First paragraph."))
        self.assertTrue(state.mark_if_changed("", "First paragraph.\nSecond paragraph."))

    def test_empty_transcripts_do_not_trigger(self):
        state = AutoWhisperState()

        self.assertFalse(state.mark_if_changed("", "   \n "))

    def test_auto_whisper_request_is_contextual_and_compact(self):
        request = build_auto_whisper_request("I said we should debounce it.", "They asked if it will loop.")

        self.assertIn("[OTHER PARTICIPANT", request)
        self.assertIn("[YOU", request)
        self.assertIn("Auto Whisper task", request)
        self.assertIn("Do not ask questions", request)
        self.assertIn("1 to 3 short paragraphs", request)

    def test_auto_whisper_prompt_discourages_infinite_questions(self):
        prompt = analyzer.AUTO_WHISPER_PROMPT

        self.assertIn("Do not ask questions", prompt)
        self.assertIn("Never generate follow-up questions", prompt)
        self.assertIn("1 to 3 short paragraphs", prompt)
        self.assertIn("prior responses", prompt)


if __name__ == "__main__":
    unittest.main()
