import unittest

from context_memory import ContextMemory


class ContextMemoryTests(unittest.TestCase):
    def test_keeps_recent_entries_bounded_by_count(self):
        memory = ContextMemory(max_entries=3, max_chars=10_000)

        for index in range(5):
            memory.add("auto_whisper", f"request {index}", f"response {index}")

        block = memory.build_context_block()

        self.assertNotIn("response 0", block)
        self.assertNotIn("response 1", block)
        self.assertIn("response 2", block)
        self.assertIn("response 3", block)
        self.assertIn("response 4", block)

    def test_build_context_block_uses_newest_entries_within_budget(self):
        memory = ContextMemory(max_entries=10, max_chars=120)
        memory.add("screenshot", "old screen", "old analysis " * 20)
        memory.add("screenshot", "new screen", "new analysis")

        block = memory.build_context_block()

        self.assertIn("new screen", block)
        self.assertIn("new analysis", block)
        self.assertNotIn("old analysis", block)
        self.assertIn("Use this only when relevant", block)

    def test_latest_exchange_returns_last_saved_pair(self):
        memory = ContextMemory(max_entries=3, max_chars=10_000)
        memory.add("audio", "first request", "first response")
        memory.add("screenshot", "second request", "second response")

        self.assertEqual(memory.latest_exchange(), ("second request", "second response"))

    def test_recent_entries_returns_last_entries_in_chronological_order(self):
        memory = ContextMemory(max_entries=5, max_chars=10_000)
        for index in range(5):
            memory.add("auto_whisper", f"request {index}", f"response {index}")

        entries = memory.recent_entries(limit=3)

        self.assertEqual([entry.response for entry in entries], ["response 2", "response 3", "response 4"])

    def test_ignores_empty_entries(self):
        memory = ContextMemory(max_entries=3, max_chars=10_000)

        memory.add("audio", "request only", "")

        self.assertEqual(memory.latest_exchange(), None)
        self.assertEqual(memory.build_context_block(), "")


if __name__ == "__main__":
    unittest.main()
