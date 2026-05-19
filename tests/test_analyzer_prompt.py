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

    def test_vision_prompt_preserves_screenshot_continuity_and_file_boundaries(self):
        prompt = analyzer.VISION_PROMPT

        self.assertIn("cumulative screen-reading task", prompt)
        self.assertIn("Do not treat the latest screenshot as the full context", prompt)
        self.assertIn("continue from the previous screenshot context", prompt)
        self.assertIn("clear context", prompt)
        self.assertIn("separate sections for each file", prompt)
        self.assertIn("Final File Checklist", prompt)

    def test_analyze_text_accepts_recent_context_memory(self):
        fake_client = FakeTextClient()
        original_get_text_client = analyzer._get_text_client
        original_provider = analyzer.LLM_TEXT_PROVIDER

        try:
            analyzer.LLM_TEXT_PROVIDER = "openai"
            analyzer._get_text_client = lambda: fake_client
            analyzer.analyze_text(
                "new question",
                recent_context="Recent context memory. Use only if relevant. Previous useful answer.",
            )
        finally:
            analyzer._get_text_client = original_get_text_client
            analyzer.LLM_TEXT_PROVIDER = original_provider

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
        original_provider = analyzer.LLM_TEXT_PROVIDER

        try:
            analyzer.LLM_TEXT_PROVIDER = "openai"
            analyzer._get_text_client = lambda: fake_client
            analyzer.analyze_transcript(
                "",
                "They asked about the previous answer.",
                recent_context="Recent context memory. Previous screenshot answer.",
            )
        finally:
            analyzer._get_text_client = original_get_text_client
            analyzer.LLM_TEXT_PROVIDER = original_provider

        messages = fake_client.create_kwargs["messages"]
        self.assertTrue(
            any(
                message["role"] == "system" and "Previous screenshot answer" in message["content"]
                for message in messages
            )
        )

    def test_analyze_screenshot_forwards_full_recent_context(self):
        fake_client = FakeTextClient()
        original_get_image_client = analyzer._get_image_client
        original_provider = analyzer.LLM_IMAGE_PROVIDER
        original_prepare_vision_views = analyzer.prepare_vision_views
        long_context = "SCREEN_CONTEXT_START " + ("folder/api/model/view/controller " * 400) + "SCREEN_CONTEXT_END"

        try:
            analyzer.LLM_IMAGE_PROVIDER = "openai"
            analyzer._get_image_client = lambda: fake_client
            analyzer.prepare_vision_views = lambda _image_bytes: [
                {
                    "bytes": b"fake-png",
                    "mime_type": "image/png",
                    "label": "full screen",
                    "width": 100,
                    "height": 50,
                }
            ]
            analyzer.analyze_screenshot(b"original", recent_context=long_context)
        finally:
            analyzer._get_image_client = original_get_image_client
            analyzer.LLM_IMAGE_PROVIDER = original_provider
            analyzer.prepare_vision_views = original_prepare_vision_views

        messages = fake_client.create_kwargs["messages"]
        text_parts = [
            item["text"]
            for item in messages[0]["content"]
            if item.get("type") == "text"
        ]
        joined_text = "\n".join(text_parts)
        self.assertIn("SCREEN_CONTEXT_START", joined_text)
        self.assertIn("SCREEN_CONTEXT_END", joined_text)
        self.assertIn(long_context, joined_text)


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
