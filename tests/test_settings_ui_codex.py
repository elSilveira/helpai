import logging
import unittest

import settings_ui
from settings_ui import SettingsWindow


class SettingsUiCodexTests(unittest.TestCase):
    def test_combo_widget_registry_is_created_lazily_for_existing_instances(self):
        window = SettingsWindow.__new__(SettingsWindow)

        registry = window._ensure_combo_widget_registry()

        self.assertEqual(registry, {})
        self.assertIs(window._combo_widgets, registry)

    def test_openai_model_dropdowns_include_gpt_5_5_and_vision_capable_models(self):
        text_model_ids = [model_id for _label, model_id in settings_ui._OPENAI_TEXT_MODELS]
        image_model_ids = [model_id for _label, model_id in settings_ui._OPENAI_IMAGE_MODELS]

        self.assertIn("gpt-5.5", text_model_ids)
        self.assertIn("gpt-5.5", image_model_ids)
        self.assertIn("gpt-5.2", text_model_ids)
        self.assertIn("gpt-5.2", image_model_ids)
        self.assertIn("gpt-4o-mini", text_model_ids)
        self.assertIn("gpt-4o-mini", image_model_ids)
        self.assertNotIn("o3-mini", image_model_ids)

    def test_collect_preserves_custom_editable_combo_values(self):
        window = SettingsWindow.__new__(SettingsWindow)
        variable = FakeStringVar("gpt-new-preview")
        window.data = {"OPENAI_TEXT_MODEL": "gpt-4o"}
        window._entries = {"OPENAI_TEXT_MODEL": variable}
        window._choice_maps = {
            "OPENAI_TEXT_MODEL": {
                "GPT-4o": "gpt-4o",
            }
        }

        collected = window._collect()

        self.assertEqual(collected["OPENAI_TEXT_MODEL"], "gpt-new-preview")

    def test_loading_finishes_when_background_probe_fails(self):
        window = SettingsWindow.__new__(SettingsWindow)
        window.data = {"LLM_TEXT_PROVIDER": "openai", "LLM_IMAGE_PROVIDER": "openai"}
        window.root = FakeRoot()
        window._finish_build = object()
        old_mics = settings_ui.list_microphone_choices
        old_speakers = settings_ui.list_speaker_choices
        settings_ui.list_microphone_choices = failing_probe
        settings_ui.list_speaker_choices = failing_probe
        logging.disable(logging.CRITICAL)
        try:
            window._load_data_async()
        finally:
            logging.disable(logging.NOTSET)
            settings_ui.list_microphone_choices = old_mics
            settings_ui.list_speaker_choices = old_speakers

        self.assertEqual(window.root.callbacks, [(0, window._finish_build)])
        self.assertEqual(window._mic_choices, [("System default mic", "")])
        self.assertEqual(window._spk_choices, [("System default output", "")])


class FakeStringVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class FakeRoot:
    def __init__(self):
        self.callbacks = []

    def after(self, delay, callback):
        self.callbacks.append((delay, callback))


def failing_probe():
    raise RuntimeError("probe failed")


if __name__ == "__main__":
    unittest.main()
