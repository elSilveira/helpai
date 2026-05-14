import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HiddenBootstrapLauncherTests(unittest.TestCase):
    def test_hidden_launcher_delegates_to_bootstrap_without_showing_a_window(self):
        launcher = (ROOT / "simple_launcher_hidden.vbs").read_text(encoding="utf-8")

        self.assertIn("bootstrap_launcher.ps1", launcher)
        self.assertIn("powershell.exe", launcher)
        self.assertIn("-WindowStyle Hidden", launcher)
        self.assertIn("shell.Run", launcher)
        self.assertIn(", 0, False", launcher)

    def test_bootstrap_launcher_provisions_runtime_and_launches_with_pythonw(self):
        bootstrap = (ROOT / "bootstrap_launcher.ps1").read_text(encoding="utf-8")

        self.assertIn("Start-Transcript", bootstrap)
        self.assertIn("Find-Python", bootstrap)
        self.assertIn("Install-PythonWithWinget", bootstrap)
        self.assertIn("Python.Python.3.12", bootstrap)
        self.assertIn("-m venv", bootstrap)
        self.assertIn("requirements.txt", bootstrap)
        self.assertIn("pip", bootstrap)
        self.assertIn("pythonw.exe", bootstrap)
        self.assertIn("launcher.py", bootstrap)
        self.assertIn("WScript.Shell", bootstrap)
        self.assertIn("Assert-PathInsideRoot", bootstrap)
        self.assertIn("GetFullPath", bootstrap)


if __name__ == "__main__":
    unittest.main()
