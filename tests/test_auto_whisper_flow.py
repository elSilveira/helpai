import ast
import unittest
from pathlib import Path

from auto_whisper import AUTO_WHISPER_DEBOUNCE_SECONDS


ROOT = Path(__file__).resolve().parents[1]


def _function_node(source: str, name: str) -> ast.FunctionDef:
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function {name!r} not found")


class AutoWhisperFlowTests(unittest.TestCase):
    def test_auto_whisper_debounce_is_fast_enough_for_live_help(self):
        self.assertLessEqual(AUTO_WHISPER_DEBOUNCE_SECONDS, 1.0)

    def test_auto_whisper_does_not_wait_for_audio_levels_to_go_idle(self):
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        run_auto = _function_node(main_source, "_run_auto_whisper")

        called_names = {
            node.func.id
            for node in ast.walk(run_auto)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

        self.assertNotIn("_capture_has_active_audio", called_names)

    def test_auto_whisper_runs_for_each_changed_transcript_without_threshold_gates(self):
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        run_auto = _function_node(main_source, "_run_auto_whisper")

        called_attributes = {
            node.func.attr
            for node in ast.walk(run_auto)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

        self.assertIn("mark_if_changed", called_attributes)
        self.assertNotIn("build_request_if_ready", called_attributes)
        self.assertNotIn("retry_after_seconds", called_attributes)

    def test_enabling_auto_whisper_schedules_current_transcript_check(self):
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        toggle = _function_node(main_source, "_set_auto_whisper_enabled")

        schedule_calls = [
            node
            for node in ast.walk(toggle)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_schedule_auto_whisper"
        ]

        self.assertEqual(1, len(schedule_calls))

    def test_audio_shortcut_uses_same_whisper_request_and_analyzer_as_auto(self):
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        audio_action = _function_node(main_source, "_action_audio_analysis")

        called_names = {
            node.func.id
            for node in ast.walk(audio_action)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

        self.assertIn("build_auto_whisper_request", called_names)
        self.assertIn("analyze_auto_whisper", called_names)
        self.assertNotIn("analyze_transcript", called_names)


if __name__ == "__main__":
    unittest.main()
