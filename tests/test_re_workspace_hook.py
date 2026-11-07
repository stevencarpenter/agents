import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "tools" / "hooks" / "re-workspace-context.sh"


def _run(cwd: Path, stdin: str = "") -> str:
    env = dict(os.environ, RE_HOOK_CWD=str(cwd))
    out = subprocess.run([str(HOOK)], input=stdin, capture_output=True, text=True, env=env, check=True)
    return out.stdout


class ReWorkspaceHookTests(unittest.TestCase):
    def test_silent_outside_re_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_run(Path(tmp)), "")

    def test_workspace_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "findings").mkdir()
            (root / "evidence").mkdir()
            out = _run(root)
            self.assertIn("kind: workspace", out)
            self.assertIn("snapshot_path", out)
            self.assertIn("re-provenance-guidelines", out)

    def test_package_detected_by_label_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SPEC").mkdir()
            (root / "SPEC" / "README.md").write_text("| **Observed** | Read from the binary |\n")
            self.assertIn("kind: package", _run(root))

    def test_consumer_detected_by_vendored_sums(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "research" / "pkg").mkdir(parents=True)
            (root / "docs" / "research" / "pkg" / "SHA256SUMS").write_text("x\n")
            self.assertIn("kind: consumer", _run(root))

    def test_cwd_read_from_hook_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "findings").mkdir()
            (root / "evidence").mkdir()
            env = dict(os.environ)
            env.pop("RE_HOOK_CWD", None)
            out = subprocess.run(
                [str(HOOK)],
                input='{"session_id": "s", "cwd": "%s"}' % root,
                capture_output=True,
                text=True,
                env=env,
                check=True,
                cwd=tmp,
            ).stdout
            self.assertIn("kind: workspace", out)


if __name__ == "__main__":
    unittest.main()
