import unittest
from types import SimpleNamespace

import analyzer


class AnalyzerPromptTests(unittest.TestCase):
    def test_text_prompt_prefers_short_paragraph_insights(self):
        prompt = analyzer.SYSTEM_PROMPT

        self.assertIn("2 to 4 short paragraphs", prompt)
        self.assertIn("last exchange", prompt)
        self.assertIn("Do not restate the transcript", prompt)
        self.assertNotIn("ALWAYS use bullet points", prompt)
        self.assertNotIn("Give FULL, COMPLETE responses", prompt)

    def test_text_prompt_orders_explanation_before_code(self):
        prompt = analyzer.SYSTEM_PROMPT

        self.assertIn("explain the approach first", prompt)
        self.assertIn("then provide the code", prompt)
        self.assertIn("then explain why", prompt)

    def test_vision_prompt_orders_explanation_before_code(self):
        prompt = analyzer.VISION_PROMPT

        self.assertIn("FIRST explain my approach", prompt)
        self.assertIn("THEN provide", prompt)
        self.assertIn("THEN explain why", prompt)

    def test_analyze_text_accepts_recent_context_memory(self):
        fake_client = FakeTextClient()
        original_get_text_client = analyzer._get_text_client

        try:
            analyzer._get_text_client = lambda: fake_client
            analyzer.analyze_text(
                "new question",
                recent_context="Recent context memory. Use only if relevant. Previous useful answer.",
            )
        finally:
            analyzer._get_text_client = original_get_text_client

        messages = fake_client.create_kwargs["messages"]
        self.assertEqual(messages[-1]["content"], "new question")
        self.assertTrue(
            any(
                message["role"] == "system" and "Previous useful answer" in message["content"]
                for message in messages
            )
        )

    def test_analyze_transcript_forwards_recent_context_memory(self):
        fake_client = FakeTextClient()
        original_get_text_client = analyzer._get_text_client

        try:
            analyzer._get_text_client = lambda: fake_client
            analyzer.analyze_transcript(
                "",
                "They asked about the previous answer.",
                recent_context="Recent context memory. Previous screenshot answer.",
            )
        finally:
            analyzer._get_text_client = original_get_text_client

        messages = fake_client.create_kwargs["messages"]
        self.assertTrue(
            any(
                message["role"] == "system" and "Previous screenshot answer" in message["content"]
                for message in messages
            )
        )


class FakeTextClient:
    def __init__(self):
        self.create_kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.create_kwargs = kwargs
        message = SimpleNamespace(content="covered")
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


if __name__ == "__main__":
    unittest.main()
