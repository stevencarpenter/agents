"""Tests for mining/mine_hippo.py."""

import importlib.util
import io
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

_SPEC = importlib.util.spec_from_file_location(
    "mine_hippo", Path(__file__).resolve().parents[1] / "mining" / "mine_hippo.py"
)
mine_hippo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mine_hippo)


class MineHippoTest(unittest.TestCase):
    def mine(self, project_dirs: list[str]) -> tuple[list[str], str]:
        """Run the miner over one delegated session per project dir; return (file names, stdout)."""
        with tempfile.TemporaryDirectory() as tmp:
            db, out = Path(tmp) / "hippo.db", Path(tmp) / "candidates"
            with closing(sqlite3.connect(db)) as connection:
                connection.execute(
                    "CREATE TABLE agentic_sessions"
                    " (project_dir TEXT, session_id TEXT, harness TEXT, is_subagent INT, probe_tag TEXT)"
                )
                connection.executemany(
                    "INSERT INTO agentic_sessions VALUES (?, ?, 'claude-code', 1, NULL)",
                    [(project_dir, f"s{n}") for n, project_dir in enumerate(project_dirs)],
                )
                connection.commit()
            stdout = io.StringIO()
            with (
                patch("sys.argv", ["mine_hippo.py", "--db", str(db), "--out", str(out)]),
                patch.object(Path, "home", return_value=Path("/home/tester")),
                redirect_stdout(stdout),
            ):
                self.assertEqual(mine_hippo.main(), 0)
            return sorted(path.name for path in out.iterdir()), stdout.getvalue()

    def test_candidate_is_named_after_the_project_not_the_home_path(self) -> None:
        names, _ = self.mine(["-home-tester-projects-alpha"])
        self.assertEqual(names, ["alpha.md"])

    def test_reported_count_is_the_number_of_files_written(self) -> None:
        names, stdout = self.mine(["-home-tester-projects-alpha", "---"])
        self.assertEqual(len(names), 1)
        self.assertIn("wrote 1 candidate", stdout)


if __name__ == "__main__":
    unittest.main()
