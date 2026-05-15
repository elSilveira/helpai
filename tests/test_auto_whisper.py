import unittest
from types import SimpleNamespace

import analyzer
from auto_whisper import (
    AUTO_WHISPER_COOLDOWN_SECONDS,
    AUTO_WHISPER_MIN_NEW_CHARS,
    AutoWhisperState,
    build_auto_whisper_request,
)


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

    def test_auto_whisper_waits_for_meaningful_new_text(self):
        state = AutoWhisperState()

        self.assertIsNone(state.build_request_if_ready("", "Too short.", now=1.0))

        request = state.build_request_if_ready(
            "",
            "They explained the customer issue and asked us to slow down the automatic "
            "assistant so it waits for a stable point before spending tokens.",
            now=2.0,
        )

        self.assertIsNotNone(request)

    def test_auto_whisper_respects_cooldown_without_marking_text_sent(self):
        state = AutoWhisperState()
        first_text = "A" * AUTO_WHISPER_MIN_NEW_CHARS
        second_text = first_text + ("B" * AUTO_WHISPER_MIN_NEW_CHARS)

        self.assertIsNotNone(state.build_request_if_ready("", first_text, now=10.0))
        self.assertIsNone(state.build_request_if_ready("", second_text, now=10.0 + 1.0))

        request = state.build_request_if_ready(
            "",
            second_text,
            now=10.0 + AUTO_WHISPER_COOLDOWN_SECONDS + 0.1,
        )

        self.assertIsNotNone(request)
        self.assertIn("B" * AUTO_WHISPER_MIN_NEW_CHARS, request)
        self.assertNotIn("A" * AUTO_WHISPER_MIN_NEW_CHARS, request)

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

    def test_auto_whisper_keeps_newest_recent_context_when_bounded(self):
        fake_client = FakeTextClient()
        original_get_text_client = analyzer._get_text_client

        try:
            analyzer._get_text_client = lambda: fake_client
            analyzer.analyze_auto_whisper(
                "current transcript",
                recent_context=("old context " * 700) + "LATEST_CONTEXT_TAIL",
            )
        finally:
            analyzer._get_text_client = original_get_text_client

        messages = fake_client.create_kwargs["messages"]
        context_messages = [
            message["content"]
            for message in messages
            if message["role"] == "system" and "old context" in message["content"]
        ]
        self.assertEqual(len(context_messages), 1)
        self.assertIn("LATEST_CONTEXT_TAIL", context_messages[0])

    def test_auto_whisper_keeps_newest_last_exchange_when_bounded(self):
        fake_client = FakeTextClient()
        original_get_text_client = analyzer._get_text_client

        try:
            analyzer._get_text_client = lambda: fake_client
            analyzer.analyze_auto_whisper(
                "current transcript",
                last_exchange=(
                    ("previous request " * 250) + "LATEST_REQUEST_TAIL",
                    ("previous response " * 250) + "LATEST_RESPONSE_TAIL",
                ),
            )
        finally:
            analyzer._get_text_client = original_get_text_client

        messages = fake_client.create_kwargs["messages"]
        self.assertIn("LATEST_REQUEST_TAIL", messages[1]["content"])
        self.assertIn("LATEST_RESPONSE_TAIL", messages[2]["content"])


class FakeTextClient:
    def __init__(self):
        self.create_kwargs = None
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.create_kwargs = kwargs
        message = SimpleNamespace(content="covered")
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


if __name__ == "__main__":
    unittest.main()
