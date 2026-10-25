"""Tests for blind-review benchmark scoring, the findings ledger, and the sandbox."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from unittest import mock

SKILL = Path(__file__).resolve().parents[1] / "skills/blind-review"


def load(name: str, path: Path) -> ModuleType:
    """Load a script as a module despite its location outside a package.

    Args:
        name: Module name to register.
        path: Script path.

    Returns:
        The imported module.
    """
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


bench = load("bench", SKILL / "bench/bench.py")
mechanical_review = load("mechanical_review_t", SKILL / "scripts/mechanical_review.py")

CASE = {
    "id": "t",
    "traps": [
        {"id": "bug", "kind": "bug", "path": "a.py", "anchors": [["+", 5]]},
        {"id": "safe", "kind": "safe", "path": "a.py", "anchors": [["+", 9]]},
    ],
}
UNITS = {"a.py": "f01.py"}


def finding(side: str, line: int, severity: str = "medium") -> dict:
    """Build a minimal finding."""
    return {"side": side, "line": line, "severity": severity}


class BenchScoringTest(unittest.TestCase):
    """A trap outcome must follow the anchor, side, and severity rules exactly."""

    def score(self, *findings: dict) -> dict:
        """Score one rep whose only unit has ``findings``."""
        return bench.score_rep(CASE, UNITS, {"f01.py": {"findings": list(findings)}})

    def test_unknown_case_id_is_refused(self) -> None:
        """A typo must not record an empty run as a result."""
        with self.assertRaises(SystemExit):
            bench.main(["run", "--case", "c99-typo", "--record"])

    def test_fixture_commits_ignore_user_git_config(self) -> None:
        """A global signing setup must not break the fixture repos."""
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "gitconfig"
            config.write_text("[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = /nonexistent-gpg\n")
            with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config)}):
                bench.build_units(bench.load_cases()[0], Path(tmp) / "case")

    def test_bug_hit_within_one_line_on_the_same_side(self) -> None:
        """Line 6 is within tolerance of anchor 5; the other side is not."""
        self.assertTrue(self.score(finding("+", 6))["outcome"]["bug"])
        self.assertFalse(self.score(finding("-", 5))["outcome"]["bug"])
        self.assertFalse(self.score(finding("+", 7))["outcome"]["bug"])

    def test_low_severity_on_a_safe_trap_is_not_a_false_alarm(self) -> None:
        """Only medium or high findings on correct code count against the reviewer."""
        self.assertFalse(self.score(finding("+", 9, "low"))["outcome"]["safe"])
        self.assertTrue(self.score(finding("+", 9, "high"))["outcome"]["safe"])

    def test_unmatched_findings_are_counted_as_extra(self) -> None:
        """A finding on no trap is noise the scores must show."""
        self.assertEqual(self.score(finding("+", 5), finding("+", 30))["extra"], 1)

    def test_failed_reviews_are_not_scored_or_recorded(self) -> None:
        """A failed rep must not read as a clean review, and the run must not be recorded."""
        failed = {"ok": False, "findings": [], "usage": None, "model_id": "",
                  "input_sha256": "x", "error": "api down"}
        results = Path(tempfile.mkdtemp()) / "results.jsonl"
        self.addCleanup(shutil.rmtree, results.parent, ignore_errors=True)
        with (
            mock.patch.object(bench.mechanical_review, "review_unit", return_value=failed),
            mock.patch.object(bench.mechanical_review, "cli_version", return_value="t"),
            mock.patch.object(bench, "RESULTS", results),
            mock.patch("sys.stdout", new=io.StringIO()) as stdout,
            mock.patch("sys.stderr", new=io.StringIO()),
        ):
            code = bench.main(["run", "--reps", "2", "--case", "c01-py-path-guard-removed", "--record"])
        self.assertEqual(code, 1)
        self.assertFalse(results.exists())
        text = stdout.getvalue()
        scores = json.JSONDecoder().raw_decode(text, text.index("{\n"))[0]["scores"]
        self.assertIsNone(scores["recall"])
        self.assertIsNone(scores["trap_stability"])
        self.assertIsNone(scores["finding_jaccard"])

    def test_jaccard(self) -> None:
        """Identical sets score 1, disjoint sets 0, empty reps count as agreement."""
        self.assertEqual(bench.jaccard([{1}, {1}]), 1.0)
        self.assertEqual(bench.jaccard([{1}, {2}]), 0.0)
        self.assertEqual(bench.jaccard([set(), set()]), 1.0)

    def test_every_case_anchor_is_a_unit_row(self) -> None:
        """A trap whose anchors are not in the unit can never be hit."""
        with tempfile.TemporaryDirectory() as tmp:
            for case in bench.load_cases():
                bench.build_units(case, Path(tmp) / case["id"])


class ReviewLogTest(unittest.TestCase):
    """The ledger must keep the latest verdict and detect addressed lines."""

    def setUp(self) -> None:
        """Point the ledger at a temp file and build one mechanical out dir."""
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        patcher = mock.patch.dict(os.environ, {"BLIND_REVIEW_LEDGER": str(self.tmp / "l.jsonl")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.log = load("review_log_t", SKILL / "scripts/review_log.py")
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        (self.repo / "a.py").write_text("x = 1\ny = eval(s)\n")
        out = self.tmp / "run1"
        (out / "units").mkdir(parents=True)
        (out / "results").mkdir()
        (out / "manifest.json").write_text(json.dumps({
            "repo": str(self.repo), "base": "HEAD",
            "files": [{"path": "a.py", "action": "stripped", "unit": "f01.py"}],
        }))
        (out / "units" / "f01.py.diff").write_text("file f01.py\n+2|y = eval(s)\n")
        (out / "results" / "f01.py.json").write_text(json.dumps({
            "unit": "f01.py", "model_id": "m",
            "findings": [{"side": "+", "line": 2, "severity": "high", "confidence": "high",
                          "category": "security", "claim": "eval on input"}],
        }))
        self.out = out

    def test_log_is_idempotent_and_mark_wins(self) -> None:
        """Logging the same run twice adds nothing; the latest mark is the status."""
        self.log.main(["log", "--out", str(self.out)])
        self.log.main(["log", "--out", str(self.out)])
        findings = self.log.load()[0]
        self.assertEqual(len(findings), 1)
        (fid,) = findings
        self.assertEqual(findings[fid]["line_text"], "y = eval(s)")
        self.log.main(["mark", fid, "false-positive"])
        self.log.main(["mark", fid, "accepted"])
        self.assertEqual(self.log.load()[0][fid]["status"], "accepted")

    def test_ids_depend_on_repo_and_reviewed_text(self) -> None:
        """Same out dir name in another repo, or new unit text, is a new finding."""
        self.log.main(["log", "--out", str(self.out)])
        other = self.tmp / "other" / self.out.name
        shutil.copytree(self.out, other)
        manifest = json.loads((other / "manifest.json").read_text())
        manifest["repo"] = str(self.tmp / "repo2")
        (other / "manifest.json").write_text(json.dumps(manifest))
        self.log.main(["log", "--out", str(other)])
        self.assertEqual(len(self.log.load()[0]), 2)
        (self.out / "units" / "f01.py.diff").write_text("file f01.py\n+2|y = eval(t)\n")
        self.log.main(["log", "--out", str(self.out)])
        self.assertEqual(len(self.log.load()[0]), 3)

    def test_reconcile_marks_changed_lines_only(self) -> None:
        """An unchanged flagged line stays open; a rewritten one is likely-addressed."""
        self.log.main(["log", "--out", str(self.out)])
        self.log.main(["reconcile"])
        (fid,) = self.log.load()[0]
        self.assertEqual(self.log.load()[0][fid]["status"], "open")
        (self.repo / "a.py").write_text("x = 1\ny = int(s)\n")
        self.log.main(["reconcile"])
        self.assertEqual(self.log.load()[0][fid]["status"], "likely-addressed")

    def test_reconcile_keeps_a_moved_but_unchanged_line_open(self) -> None:
        """Imports added above the flagged line move it; that is not a fix."""
        self.log.main(["log", "--out", str(self.out)])
        (self.repo / "a.py").write_text("import a\nimport b\nimport c\nimport d\nimport e\nx = 1\ny = eval(s)\n")
        self.log.main(["reconcile"])
        (fid,) = self.log.load()[0]
        self.assertEqual(self.log.load()[0][fid]["status"], "open")

    def test_failed_review_is_reported_not_logged_as_clean(self) -> None:
        """A failed unit must not read as a file with no findings."""
        (self.out / "results" / "f01.py.json").write_text(
            json.dumps({"unit": "f01.py", "ok": False, "error": "api down", "findings": []})
        )
        self.assertEqual(self.log.main(["log", "--out", str(self.out)]), 1)
        self.assertEqual(self.log.load()[0], {})

    def test_duplicate_findings_in_one_run_log_once(self) -> None:
        """Two identical findings in one result are one finding."""
        result = json.loads((self.out / "results" / "f01.py.json").read_text())
        result["findings"] *= 2
        (self.out / "results" / "f01.py.json").write_text(json.dumps(result))
        self.log.main(["log", "--out", str(self.out)])
        self.assertEqual(len(self.log.LEDGER.read_text().splitlines()), 1)

    def test_torn_ledger_line_is_skipped(self) -> None:
        """A write cut short must not make every later command fail."""
        self.log.main(["log", "--out", str(self.out)])
        with self.log.LEDGER.open("a") as fh:
            fh.write('{"type":"fin')
        (fid,) = self.log.load()[0]
        self.log.main(["mark", fid, "accepted"])
        self.assertEqual(self.log.load()[0][fid]["status"], "accepted")

    def test_reconcile_ignores_an_unchanged_inline_comment(self) -> None:
        """The logged text is comment-free, so the current file must be stripped too."""
        (self.repo / "a.py").write_text("x = 1\ny = eval(s)  # safe\n")
        self.log.main(["log", "--out", str(self.out)])
        self.log.main(["reconcile"])
        (fid,) = self.log.load()[0]
        self.assertEqual(self.log.load()[0][fid]["status"], "open")


class SandboxTest(unittest.TestCase):
    """The fixed reviewer cwd must stay empty and must not name the repo."""

    def test_refuses_non_empty_or_repo_named_sandbox(self) -> None:
        """Either condition would put non-diff text in front of the model."""
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "blind-review-sandbox"
            with mock.patch.object(mechanical_review, "SANDBOX", box):
                self.assertEqual(mechanical_review.sandbox("repo-x"), box)
                with self.assertRaises(SystemExit):
                    mechanical_review.sandbox("blind-review")
                (box / "stray.txt").write_text("x")
                with self.assertRaises(SystemExit):
                    mechanical_review.sandbox("repo-x")

    def test_refuses_symlinked_sandbox(self) -> None:
        """On a shared /tmp another user could point the path at their own directory."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "elsewhere"
            target.mkdir()
            box = Path(tmp) / "blind-review-sandbox"
            box.symlink_to(target)
            with mock.patch.object(mechanical_review, "SANDBOX", box):
                with self.assertRaises(SystemExit):
                    mechanical_review.sandbox("repo-x")


if __name__ == "__main__":
    unittest.main()
