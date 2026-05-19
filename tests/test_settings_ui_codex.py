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


class FakeStringVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


if __name__ == "__main__":
    unittest.main()
