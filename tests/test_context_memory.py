import unittest

from context_memory import ContextMemory, should_continue_screen_context_session


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

    def test_latest_screenshot_entry_is_kept_complete_even_over_budget(self):
        memory = ContextMemory(max_entries=10, max_chars=120)
        long_screen_context = "SCREEN_CONTEXT_START " + ("module context " * 40) + "SCREEN_CONTEXT_END"

        memory.add("audio", "old request", "old response")
        memory.add("screenshot", "latest screen", long_screen_context)

        block = memory.build_context_block()

        self.assertIn("latest screen", block)
        self.assertIn("SCREEN_CONTEXT_START", block)
        self.assertIn("SCREEN_CONTEXT_END", block)
        self.assertIn(long_screen_context, block)

    def test_screenshot_exchanges_build_cumulative_screen_context_session(self):
        memory = ContextMemory(max_entries=10, max_chars=2_000)

        memory.add(
            "screenshot",
            "Screenshot feedback request",
            (
                "## Insight\n"
                "- Requirement: implement account search.\n"
                "- Visible files include `search.py`.\n\n"
                "## Final File Checklist\n"
                "- `search.py` - update the Search class.\n"
            ),
        )
        memory.add(
            "screenshot",
            "Screenshot feedback request",
            (
                "## Insight\n"
                "- Second screen shows debounce requirements.\n"
                "- Visible files include `tests/test_search.py`.\n\n"
                "## Final File Checklist\n"
                "- `tests/test_search.py` - inspect and run.\n"
            ),
        )

        block = memory.build_context_block()

        self.assertIsNotNone(memory.screen_context)
        self.assertEqual(len(memory.screen_context.screenshots), 2)
        self.assertIn("Cumulative screen context session", block)
        self.assertIn("Screenshots captured: 2", block)
        self.assertIn("implement account search", block)
        self.assertIn("debounce requirements", block)
        self.assertIn("search.py", block)
        self.assertIn("tests/test_search.py", block)

    def test_screenshot_context_preserves_previous_file_change_code(self):
        memory = ContextMemory(max_entries=10, max_chars=4_000)

        memory.add(
            "screenshot",
            "Screenshot feedback request",
            (
                "## File Changes\n"
                "### `search.py`\n"
                "Change: update the Search class.\n"
                "```python\n"
                "class Search:\n"
                "    def run(self):\n"
                "        return 'updated'\n"
                "```\n\n"
                "## Final File Checklist\n"
                "- `search.py` - change: update the Search class.\n"
            ),
        )

        block = memory.build_context_block()

        self.assertIn("Previous per-file changes from the latest screenshot response", block)
        self.assertIn("search.py", block)
        self.assertIn("class Search", block)
        self.assertIn("change: update the Search class", block)

    def test_screenshot_context_can_start_new_task_from_explicit_signal(self):
        memory = ContextMemory(max_entries=10, max_chars=2_000)
        memory.add("screenshot", "Screenshot feedback request", "Visible file `old_task.py`.")
        first_session_id = memory.screen_context.id

        self.assertTrue(should_continue_screen_context_session("same task, next file", memory.screen_context))
        self.assertFalse(should_continue_screen_context_session("new task: fresh challenge", memory.screen_context))

        memory.add("screenshot", "new task: fresh challenge", "Visible file `fresh_task.py`.")
        block = memory.build_context_block()

        self.assertIsNotNone(memory.screen_context)
        self.assertNotEqual(memory.screen_context.id, first_session_id)
        self.assertEqual(len(memory.screen_context.screenshots), 1)
        self.assertIn("fresh_task.py", block)
        self.assertNotIn("old_task.py", block)

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

    def test_clear_removes_all_saved_context(self):
        memory = ContextMemory(max_entries=3, max_chars=10_000)
        memory.add("screenshot", "old request", "Visible file `old_task.py`.")

        memory.clear()

        self.assertEqual(memory.latest_exchange(), None)
        self.assertEqual(memory.recent_entries(), [])
        self.assertEqual(memory.build_context_block(), "")
        self.assertIsNone(memory.screen_context)


if __name__ == "__main__":
    unittest.main()
