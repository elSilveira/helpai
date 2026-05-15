import unittest

from settings_ui import SettingsWindow


class SettingsUiCodexTests(unittest.TestCase):
    def test_combo_widget_registry_is_created_lazily_for_existing_instances(self):
        window = SettingsWindow.__new__(SettingsWindow)

        registry = window._ensure_combo_widget_registry()

        self.assertEqual(registry, {})
        self.assertIs(window._combo_widgets, registry)


if __name__ == "__main__":
    unittest.main()
