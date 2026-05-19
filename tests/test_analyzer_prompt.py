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

    def test_text_prompt_improves_after_failed_code_attempts(self):
        prompt = analyzer.SYSTEM_PROMPT

        self.assertIn("If the previous code failed", prompt)
        self.assertIn("do not return the same solution unchanged", prompt)
        self.assertIn("explain what changed", prompt)

    def test_text_prompt_requires_complexity_and_integer_limits_for_coding(self):
        prompt = analyzer.SYSTEM_PROMPT

        self.assertIn("time complexity", prompt)
        self.assertIn("space complexity", prompt)
        self.assertIn("large integer", prompt)
        self.assertIn("BigInt", prompt)

    def test_vision_prompt_orders_explanation_before_code(self):
        prompt = analyzer.VISION_PROMPT

        self.assertIn("FIRST explain my approach", prompt)
        self.assertIn("THEN provide", prompt)
        self.assertIn("THEN explain why", prompt)

    def test_vision_prompt_improves_after_failed_code_attempts(self):
        prompt = analyzer.VISION_PROMPT

        self.assertIn("If the previous code failed", prompt)
        self.assertIn("do not return the same solution unchanged", prompt)
        self.assertIn("explain what changed", prompt)

    def test_vision_prompt_requires_complexity_and_integer_limits_for_coding(self):
        prompt = analyzer.VISION_PROMPT

        self.assertIn("time complexity", prompt)
        self.assertIn("space complexity", prompt)
        self.assertIn("large integer", prompt)
        self.assertIn("BigInt", prompt)

    def test_vision_prompt_preserves_screenshot_continuity_and_file_boundaries(self):
        prompt = analyzer.VISION_PROMPT

        self.assertIn("cumulative screen-reading task", prompt)
        self.assertIn("Do not treat the latest screenshot as the full context", prompt)
        self.assertIn("continue from the previous screenshot context", prompt)
        self.assertIn("clear context", prompt)
        self.assertIn("separate sections for each file", prompt)
        self.assertIn("## File Changes", prompt)
        self.assertIn("#### File:", prompt)
        self.assertIn("This code is in", prompt)
        self.assertIn("actual replacement code", prompt)
        self.assertIn("patch-style snippet", prompt)
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

    def test_analyze_text_marks_current_feedback_as_append_after_valid_context(self):
        fake_client = FakeTextClient()
        original_get_text_client = analyzer._get_text_client
        original_provider = analyzer.LLM_TEXT_PROVIDER

        try:
            analyzer.LLM_TEXT_PROVIDER = "openai"
            analyzer._get_text_client = lambda: fake_client
            analyzer.analyze_text(
                "I passed the visible test, but the hidden case still fails.",
                last_exchange=("old problem statement", "old attempted fix"),
                recent_context="Old context: use sliding window.",
            )
        finally:
            analyzer._get_text_client = original_get_text_client
            analyzer.LLM_TEXT_PROVIDER = original_provider

        messages = fake_client.create_kwargs["messages"]
        context_message = next(
            message["content"]
            for message in messages
            if message["role"] == "system" and "Old context: use sliding window." in message["content"]
        )

        self.assertLess(messages.index({"role": "system", "content": context_message}), len(messages) - 1)
        self.assertIn("Retained context remains valid", context_message)
        self.assertIn("current request is the newest update appended after it", context_message)
        self.assertIn("test result", context_message)
        self.assertEqual(messages[-1]["content"], "I passed the visible test, but the hidden case still fails.")

    def test_analyze_text_uses_max_completion_tokens_for_gpt_5_5(self):
        fake_client = FakeTextClient()
        original_get_text_client = analyzer._get_text_client
        original_provider = analyzer.LLM_TEXT_PROVIDER
        original_model = analyzer.OPENAI_TEXT_MODEL

        try:
            analyzer.LLM_TEXT_PROVIDER = "openai"
            analyzer.OPENAI_TEXT_MODEL = "gpt-5.5"
            analyzer._get_text_client = lambda: fake_client
            analyzer.analyze_text("new question")
        finally:
            analyzer._get_text_client = original_get_text_client
            analyzer.LLM_TEXT_PROVIDER = original_provider
            analyzer.OPENAI_TEXT_MODEL = original_model

        self.assertEqual(fake_client.create_kwargs["model"], "gpt-5.5")
        self.assertIn("max_completion_tokens", fake_client.create_kwargs)
        self.assertNotIn("max_tokens", fake_client.create_kwargs)
        self.assertNotIn("temperature", fake_client.create_kwargs)

    def test_analyze_screenshot_uses_max_completion_tokens_for_gpt_5_5(self):
        fake_client = FakeTextClient()
        original_get_image_client = analyzer._get_image_client
        original_provider = analyzer.LLM_IMAGE_PROVIDER
        original_model = analyzer.OPENAI_IMAGE_MODEL
        original_prepare_vision_views = analyzer.prepare_vision_views

        try:
            analyzer.LLM_IMAGE_PROVIDER = "openai"
            analyzer.OPENAI_IMAGE_MODEL = "gpt-5.5"
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
            analyzer.analyze_screenshot(b"original")
        finally:
            analyzer._get_image_client = original_get_image_client
            analyzer.LLM_IMAGE_PROVIDER = original_provider
            analyzer.OPENAI_IMAGE_MODEL = original_model
            analyzer.prepare_vision_views = original_prepare_vision_views

        self.assertEqual(fake_client.create_kwargs["model"], "gpt-5.5")
        self.assertIn("max_completion_tokens", fake_client.create_kwargs)
        self.assertNotIn("max_tokens", fake_client.create_kwargs)

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

    def test_analyze_screenshots_sends_all_saved_images_with_code_focus(self):
        fake_client = FakeTextClient()
        original_get_image_client = analyzer._get_image_client
        original_provider = analyzer.LLM_IMAGE_PROVIDER
        original_prepare_vision_views = analyzer.prepare_vision_views

        def fake_prepare(image_bytes):
            label = image_bytes.decode("ascii")
            return [
                {
                    "bytes": image_bytes,
                    "mime_type": "image/png",
                    "label": f"{label} full screen",
                    "width": 100,
                    "height": 50,
                }
            ]

        try:
            analyzer.LLM_IMAGE_PROVIDER = "openai"
            analyzer._get_image_client = lambda: fake_client
            analyzer.prepare_vision_views = fake_prepare
            analyzer.analyze_screenshots([b"one", b"two"], recent_context="Previous file context.")
        finally:
            analyzer._get_image_client = original_get_image_client
            analyzer.LLM_IMAGE_PROVIDER = original_provider
            analyzer.prepare_vision_views = original_prepare_vision_views

        messages = fake_client.create_kwargs["messages"]
        content = messages[0]["content"]
        image_items = [item for item in content if item.get("type") == "image_url"]
        text = "\n".join(item["text"] for item in content if item.get("type") == "text")

        self.assertEqual(len(image_items), 2)
        self.assertIn("Saved screenshot batch analysis", text)
        self.assertIn("Return only the code-focused answer", text)
        self.assertIn("Screenshot 1, view 1", text)
        self.assertIn("Screenshot 2, view 1", text)
        self.assertIn("Previous file context.", text)


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
