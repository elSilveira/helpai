import unittest

from transcript_filters import format_transcript_paragraphs


class TranscriptFormattingTests(unittest.TestCase):
    def test_committed_utterance_lines_become_separate_paragraphs(self):
        raw = "We should split this by pauses.\nThat makes the live conversation easier to read."

        formatted = format_transcript_paragraphs(raw)

        self.assertEqual(
            formatted,
            "We should split this by pauses.\n\n"
            "That makes the live conversation easier to read.",
        )

    def test_extra_blank_lines_are_normalized(self):
        raw = "\n First thought. \n\n\n Second thought. \n"

        formatted = format_transcript_paragraphs(raw)

        self.assertEqual(formatted, "First thought.\n\nSecond thought.")


if __name__ == "__main__":
    unittest.main()
