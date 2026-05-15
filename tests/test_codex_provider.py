import unittest

import analyzer


class FakeCodexClient:
    def __init__(self):
        self.calls = []

    def generate_text(self, prompt, *, image_urls=None, on_token=None, model=None):
        self.calls.append(
            {
                "prompt": prompt,
                "image_urls": image_urls,
                "on_token": on_token,
                "model": model,
            }
        )
        if on_token:
            on_token("partial")
            on_token("final")
        return "final"


class CodexProviderTests(unittest.TestCase):
    def test_analyze_text_routes_codex_provider_without_openai_client(self):
        fake_codex = FakeCodexClient()
        original_provider = analyzer.LLM_TEXT_PROVIDER
        original_get_text_client = analyzer._get_text_client
        original_get_codex_client = analyzer._get_codex_client

        try:
            analyzer.LLM_TEXT_PROVIDER = "codex"
            analyzer._get_text_client = self.fail_openai_client
            analyzer._get_codex_client = lambda: fake_codex

            result = analyzer.analyze_text("new question")
        finally:
            analyzer.LLM_TEXT_PROVIDER = original_provider
            analyzer._get_text_client = original_get_text_client
            analyzer._get_codex_client = original_get_codex_client

        self.assertEqual(result, "final")
        self.assertEqual(len(fake_codex.calls), 1)
        self.assertIn(analyzer.SYSTEM_PROMPT, fake_codex.calls[0]["prompt"])
        self.assertIn("new question", fake_codex.calls[0]["prompt"])

    def test_analyze_screenshot_routes_codex_provider_with_data_url_images(self):
        fake_codex = FakeCodexClient()
        original_provider = analyzer.LLM_IMAGE_PROVIDER
        original_get_image_client = analyzer._get_image_client
        original_get_codex_client = analyzer._get_codex_client
        original_prepare_vision_views = analyzer.prepare_vision_views

        try:
            analyzer.LLM_IMAGE_PROVIDER = "codex"
            analyzer._get_image_client = self.fail_openai_client
            analyzer._get_codex_client = lambda: fake_codex
            analyzer.prepare_vision_views = lambda _image_bytes: [
                {
                    "bytes": b"fake-png",
                    "mime_type": "image/png",
                    "label": "full screen",
                    "width": 100,
                    "height": 50,
                }
            ]

            result = analyzer.analyze_screenshot(b"original")
        finally:
            analyzer.LLM_IMAGE_PROVIDER = original_provider
            analyzer._get_image_client = original_get_image_client
            analyzer._get_codex_client = original_get_codex_client
            analyzer.prepare_vision_views = original_prepare_vision_views

        self.assertEqual(result, "final")
        self.assertEqual(len(fake_codex.calls), 1)
        self.assertIn(analyzer.VISION_PROMPT, fake_codex.calls[0]["prompt"])
        self.assertEqual(
            fake_codex.calls[0]["image_urls"],
            ["data:image/png;base64,ZmFrZS1wbmc="],
        )

    def fail_openai_client(self):
        self.fail("OpenAI-compatible client should not be used for codex provider")


if __name__ == "__main__":
    unittest.main()
