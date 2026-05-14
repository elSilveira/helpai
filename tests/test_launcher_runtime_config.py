import sys
import types
import unittest
from unittest import mock

import launcher


class LauncherRuntimeConfigTests(unittest.TestCase):
    def test_launch_main_resets_runtime_modules_before_running_main(self):
        calls: list[str] = []
        fake_main = types.ModuleType("main")
        fake_main.main = lambda: calls.append("main")
        original_main = sys.modules.get("main")
        sys.modules["main"] = fake_main
        try:
            with mock.patch.object(
                launcher,
                "_discard_runtime_modules",
                side_effect=lambda: calls.append("reset"),
            ):
                launcher.launch_main()
        finally:
            if original_main is None:
                sys.modules.pop("main", None)
            else:
                sys.modules["main"] = original_main

        self.assertEqual(["reset", "main"], calls)

    def test_discard_runtime_modules_clears_config_dependent_imports(self):
        originals = {
            name: sys.modules.get(name)
            for name in launcher.RUNTIME_MODULES_TO_REIMPORT
        }
        try:
            for name in launcher.RUNTIME_MODULES_TO_REIMPORT:
                sys.modules[name] = types.ModuleType(name)

            launcher._discard_runtime_modules()

            for name in launcher.RUNTIME_MODULES_TO_REIMPORT:
                self.assertNotIn(name, sys.modules)
        finally:
            for name, module in originals.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module


if __name__ == "__main__":
    unittest.main()
