import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.verifiers.lean_verifier import LeanVerifier


class LocalLeanVerifierTests(unittest.TestCase):
    def _make_verifier(self, root: Path) -> tuple[LeanVerifier, Path, Path]:
        project = root / "project"
        project.mkdir()
        (project / "lakefile.lean").write_text("import Lake\n")

        lake = root / "lean" / "bin" / "lake"
        lake.parent.mkdir(parents=True)
        lake.write_text("")
        lake.chmod(0o755)

        config = root / "config.yaml"
        config.write_text(
            "lean:\n"
            "  method: local\n"
            "  timeout: 17\n"
            "  local:\n"
            f"    lake_path: {lake}\n"
            f"    project_path: {project}\n"
        )
        return LeanVerifier(str(config)), project, lake

    def test_local_mode_runs_lake_in_configured_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            verifier, project, lake = self._make_verifier(Path(tmp))
            completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")

            with patch("src.verifiers.lean_verifier.subprocess.run", return_value=completed) as run:
                result = verifier.verify("import Mathlib\n#check Nat\n", "", "pass/0")

            self.assertTrue(result["ok"])
            generated = Path(result["file"])
            self.assertEqual(generated.parent, project)
            self.assertTrue(generated.name.startswith("pass_0_"))
            run.assert_called_once_with(
                [str(lake), "env", "lean", generated.name],
                cwd=project,
                capture_output=True,
                text=True,
                timeout=17,
            )

    def test_missing_project_fails_before_writing_or_executing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.yaml"
            config.write_text(
                "lean:\n"
                "  method: local\n"
                "  local:\n"
                f"    project_path: {root / 'missing'}\n"
            )
            verifier = LeanVerifier(str(config))

            with patch("src.verifiers.lean_verifier.subprocess.run") as run:
                result = verifier.verify("#check Nat\n", "")

            self.assertFalse(result["ok"])
            self.assertIn("Lean project not found", result["reason"])
            self.assertIsNone(result["file"])
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
