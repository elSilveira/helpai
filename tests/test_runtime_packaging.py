import tomllib
import unittest
from pathlib import Path

import build_exe


ROOT = Path(__file__).resolve().parents[1]


class RuntimePackagingTests(unittest.TestCase):
    def test_build_exe_includes_cuda_runtime_hook(self):
        hook_paths = [Path(path).name for path in build_exe.RUNTIME_HOOKS]

        self.assertIn("rthook_cuda.py", hook_paths)

    def test_wheel_installs_windows_runtime_dependencies(self):
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = "\n".join(pyproject["project"]["dependencies"]).lower()

        self.assertIn("keyboard", dependencies)
        self.assertIn("pywin32", dependencies)
        self.assertIn("pystray", dependencies)

    def test_run_batch_launches_from_repo_root(self):
        run_script = (ROOT / "run.bat").read_text(encoding="utf-8").lower()

        self.assertIn('set "root=%~dp0"', run_script)
        self.assertIn('pushd "%root%"', run_script)
        self.assertIn("launcher.py", run_script)

    def test_run_batch_uses_selected_python_and_checks_venv_version(self):
        run_script = (ROOT / "run.bat").read_text(encoding="utf-8").lower()

        self.assertIn('set "python_exe=', run_script)
        self.assertIn("py -3.12", run_script)
        self.assertIn("venv is using an older python", run_script)
        self.assertNotIn("--upgrade pip", run_script)


if __name__ == "__main__":
    unittest.main()
