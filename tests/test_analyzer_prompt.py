import unittest

import analyzer


class AnalyzerPromptTests(unittest.TestCase):
    def test_text_prompt_prefers_short_paragraph_insights(self):
        prompt = analyzer.SYSTEM_PROMPT

        self.assertIn("2 to 4 short paragraphs", prompt)
        self.assertIn("last exchange", prompt)
        self.assertIn("Do not restate the transcript", prompt)
        self.assertNotIn("ALWAYS use bullet points", prompt)
        self.assertNotIn("Give FULL, COMPLETE responses", prompt)


if __name__ == "__main__":
    unittest.main()
