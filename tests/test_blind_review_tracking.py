"""Tests for blind-review benchmark scoring, the findings ledger, and the sandbox."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
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


GIT = shutil.which("git")
FAKE_HIPPO = """#!/bin/sh
printf '%s\n' "$*" >> "$FAKE_HIPPO_LOG"
/bin/cat "$3" > "$FAKE_HIPPO_LOG.last"
if [ "${FAKE_HIPPO_EXIT:-0}" != 0 ]; then
  echo "hippo: line 1: rejected: invalid_json" >&2
  echo "hippo: database is locked" >&2
  exit "$FAKE_HIPPO_EXIT"
fi
echo "written 1, skipped 0, rejected 0"
"""


def isolate_path(test: unittest.TestCase, tmp: Path, hippo: bool = True) -> Path:
    """Put only git and, optionally, a fake ``hippo`` on PATH; return its call log.

    The fake records its argv in the log and the file it was given in
    ``<log>.last``. ``FAKE_HIPPO_EXIT`` makes it fail. A real hippo on the
    developer's PATH is never reached.
    """
    assert GIT is not None
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(GIT)
    if hippo:
        (bin_dir / "hippo").write_text(FAKE_HIPPO)
        (bin_dir / "hippo").chmod(0o755)
    log = tmp / "hippo-calls.log"
    patcher = mock.patch.dict(os.environ, {"PATH": str(bin_dir), "FAKE_HIPPO_LOG": str(log)})
    patcher.start()
    test.addCleanup(patcher.stop)
    return log


def commit_all(repo: Path, message: str) -> str:
    """Commit every file in ``repo`` and return the full SHA."""
    bench.git(repo, "add", "-A")
    bench.git(repo, "commit", "-qm", message)
    return agent_eval.rev_parse(repo, "HEAD")


agent_eval = load("agent_eval", SKILL / "scripts/agent_eval.py")

# Section 4.3 of the agent-eval design: (required, optional) fields per record type.
CONTRACT = {
    "review_run": (
        {"id", "agent", "mode", "repo", "base", "base_sha", "head_sha", "input_sha256",
         "started_at", "finished_at"},
        {"requested_model", "model_id", "effort", "cli_version", "units_total", "units_failed",
         "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens",
         "session_id", "harness"},
    ),
    "finding": (
        {"id", "run_id", "repo", "path", "side", "line", "severity", "confidence", "claim",
         "logged_at"},
        {"line_text", "category"},
    ),
    "verdict": ({"id", "finding_id", "verdict", "auto", "decided_at"}, {"commit", "note"}),
    "escape": ({"id", "repo", "path", "line", "note", "recorded_at"}, {"fix_commit"}),
    "bench_run": (
        {"id", "bench", "recorded_at", "repo_commit", "model", "reps", "cases", "cases_sha256",
         "brief_sha256", "scores"},
        {"cli_version", "model_ids", "effort", "failed_reviews", "tokens", "per_case"},
    ),
}
SHA_FIELDS = ("base_sha", "head_sha", "commit", "fix_commit")


def assert_contract(test: unittest.TestCase, rec: dict) -> None:
    """Check one record against the v1 envelope and its type's field list."""
    test.assertEqual(rec.get("schema_version"), 1)
    required, optional = CONTRACT[rec["type"]]
    keys = rec.keys() - {"schema_version", "type"}
    test.assertLessEqual(required, keys, rec["type"])
    test.assertLessEqual(keys, required | optional, rec["type"])
    test.assertRegex(rec["id"], r"^[A-Za-z0-9._:-]{1,64}$")
    for key in keys:
        if key.endswith("_at"):
            test.assertIs(type(rec[key]), int, key)
        if key in SHA_FIELDS:
            test.assertRegex(rec[key], r"^[0-9a-f]{40}$", key)
    if rec["type"] == "verdict":
        test.assertIs(type(rec["auto"]), bool)


class AgentEvalTest(unittest.TestCase):
    """The shared helpers must match the hippo contract exactly."""

    def test_line_hash_matches_the_shared_vector(self) -> None:
        """The design's test vector keeps the Python and Rust hashes equal."""
        self.assertEqual(
            agent_eval.line_hash("    if user.is_admin or True:  \r"),
            "d5474129f47594d84b580d2b1d5d10e2ddd523ce5b0668b5de867807203e676c",
        )

    def test_line_hash_trims_ascii_space_and_tab_only(self) -> None:
        """Other Unicode whitespace is content, as in the Rust implementation."""
        self.assertEqual(agent_eval.line_hash("\tx \r"), agent_eval.line_hash("x"))
        self.assertNotEqual(agent_eval.line_hash("x "), agent_eval.line_hash("x"))

    def test_rev_parse_resolves_short_sha_and_rejects_unknown(self) -> None:
        """A short SHA becomes 40 hex; an unknown or option-like revision is an error."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            bench.git(repo, "init", "-q", "-b", "main")
            (repo / "a").write_text("a\n")
            sha = commit_all(repo, "a")
            self.assertRegex(sha, r"^[0-9a-f]{40}$")
            self.assertEqual(agent_eval.rev_parse(repo, sha[:7]), sha)
            for bad in ("deadbee", "--all", "no-such-ref"):
                with self.subTest(rev=bad), self.assertRaises(ValueError):
                    agent_eval.rev_parse(repo, bad)


class IngestTest(unittest.TestCase):
    """The local file is always written; a missing or failing hippo costs one warning."""

    def setUp(self) -> None:
        """Isolate PATH and the ledger."""
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.ledger = self.tmp / "l.jsonl"

    def escape(self) -> tuple[int, str]:
        """Record one escape and return (exit code, stderr)."""
        log = load("review_log_i", SKILL / "scripts/review_log.py")
        with (
            mock.patch.object(log, "LEDGER", self.ledger),
            mock.patch("sys.stdout", new=io.StringIO()),
            mock.patch("sys.stderr", new=io.StringIO()) as stderr,
        ):
            code = log.main(["escape", "--repo", str(self.tmp), "--path", "a.py", "--line", "3",
                             "--note", "missed"])
        return code, stderr.getvalue()

    def test_hippo_receives_the_whole_ledger(self) -> None:
        """The producer runs `hippo ingest agent-eval <ledger>` after the write."""
        calls = isolate_path(self, self.tmp)
        self.assertEqual(self.escape(), (0, ""))
        self.assertEqual(calls.read_text(), f"ingest agent-eval {self.ledger}\n")
        self.assertEqual(Path(f"{calls}.last").read_bytes(), self.ledger.read_bytes())

    def test_missing_hippo_writes_the_file_and_warns_once(self) -> None:
        """No hippo on PATH: the record is kept locally and the command succeeds."""
        isolate_path(self, self.tmp, hippo=False)
        code, stderr = self.escape()
        self.assertEqual(code, 0)
        self.assertEqual(len(stderr.splitlines()), 1)
        self.assertIn("warning: hippo not on PATH", stderr)
        self.assertEqual(len(agent_eval.read(self.ledger)), 1)

    def test_failing_hippo_writes_the_file_and_warns_once(self) -> None:
        """A non-zero ingest exit is one warning line, not a failed command."""
        isolate_path(self, self.tmp)
        with mock.patch.dict(os.environ, {"FAKE_HIPPO_EXIT": "1"}):
            code, stderr = self.escape()
        self.assertEqual(code, 0)
        self.assertEqual(len(stderr.splitlines()), 1)
        self.assertIn("exit 1: hippo: database is locked", stderr)
        self.assertEqual(len(agent_eval.read(self.ledger)), 1)


class ReviewLogTest(unittest.TestCase):
    """The ledger must hold stable v1 records, keep the effective verdict, and detect fixes."""

    def setUp(self) -> None:
        """Point the ledger at a temp file and build one git repo and mechanical out dir."""
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.calls = isolate_path(self, self.tmp)
        patcher = mock.patch.dict(os.environ, {"BLIND_REVIEW_LEDGER": str(self.tmp / "l.jsonl"),
                                               "CLAUDE_CODE_SESSION_ID": "s-env"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.log = load("review_log_t", SKILL / "scripts/review_log.py")
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        bench.git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "a.py").write_text("x = 1\ny = int(s)\n")
        self.base_sha = commit_all(self.repo, "base")
        (self.repo / "b.txt").write_text("b\n")
        self.head_sha = commit_all(self.repo, "head")
        # The reviewed tree holds an uncommitted change on top of head_sha.
        (self.repo / "a.py").write_text("x = 1\ny = eval(s)\n")
        out = self.tmp / "run1"
        (out / "units").mkdir(parents=True)
        (out / "results").mkdir()
        (out / "manifest.json").write_text(json.dumps({
            "repo": str(self.repo), "base": "HEAD", "mode": "mechanical",
            "files": [{"path": "a.py", "action": "stripped", "unit": "f01.py"}],
        }))
        self.unit = "file f01.py\n-2|y = int(s)\n+2|y = eval(s)\n"
        (out / "units" / "f01.py.diff").write_text(self.unit)
        self.write_result(self.finding())
        (out / "run.json").write_text(json.dumps({
            "started_at": 1792900000000, "finished_at": 1792900042000,
            "requested_model": "haiku", "effort": "low", "base": "HEAD",
            "base_sha": self.base_sha, "head_sha": self.head_sha, "session_id": "s-1",
            "input_tokens": 10, "output_tokens": 2, "cache_read_tokens": 30,
            "cache_creation_tokens": 0,
        }))
        self.out = out

    @staticmethod
    def finding(side: str = "+", claim: str = "eval on input") -> dict:
        """Build one reviewer finding on line 2."""
        return {"side": side, "line": 2, "severity": "high", "confidence": "high",
                "category": "security", "claim": claim, "evidence": "e"}

    def write_result(self, *findings: dict) -> None:
        """Write the unit's result file with ``findings``."""
        (self.tmp / "run1" / "results" / "f01.py.json").write_text(json.dumps({
            "unit": "f01.py", "ok": True, "model_id": "claude-haiku-5-5",
            "cli_version": "2.1.310 (Claude Code)", "input_sha256": "abc",
            "usage": {}, "findings": list(findings), "error": None,
        }))

    def run_log(self, *argv: str) -> int:
        """Run review_log.py with stdout and stderr captured; stderr lands in ``self.stderr``."""
        with (
            mock.patch("sys.stdout", new=io.StringIO()),
            mock.patch("sys.stderr", new=io.StringIO()) as stderr,
        ):
            try:
                return self.log.main(list(argv))
            finally:
                self.stderr = stderr.getvalue()

    def hippo_calls(self) -> int:
        """Return how many times the fake hippo ran."""
        return len(self.calls.read_text().splitlines()) if self.calls.exists() else 0

    def records(self, kind: str) -> list[dict]:
        """Return the ledger records of one type."""
        return [r for r in agent_eval.read(self.log.LEDGER) if r["type"] == kind]

    def only_finding(self) -> dict:
        """Return the single logged finding with its effective status."""
        (finding,) = self.log.load()[1].values()
        return finding

    def test_log_writes_one_run_then_its_findings(self) -> None:
        """The run record precedes its finding and carries the run.json facts."""
        self.assertEqual(self.run_log("log", "--out", str(self.out)), 0)
        run, finding = agent_eval.read(self.log.LEDGER)
        self.assertEqual((run["type"], finding["type"]), ("review_run", "finding"))
        for r in (run, finding):
            self.assertEqual(r["schema_version"], 1)
        self.assertEqual(finding["run_id"], run["id"])
        self.assertEqual((run["base_sha"], run["head_sha"]), (self.base_sha, self.head_sha))
        self.assertEqual(run["model_id"], "claude-haiku-5-5")
        self.assertEqual((run["units_total"], run["units_failed"]), (1, 0))
        self.assertEqual((run["session_id"], run["harness"]), ("s-1", "claude-code"))
        self.assertEqual(run["cache_read_tokens"], 30)
        self.assertEqual(finding["line_text"], "y = eval(s)")
        self.assertEqual(finding["logged_at"], 1792900042000)
        self.assertEqual(self.calls.read_text(), f"ingest agent-eval {self.log.LEDGER}\n")

    def set_run_session(self, *value: str | None) -> None:
        """Set run.json session_id to ``value``, or remove the key when no value is given."""
        meta = json.loads((self.out / "run.json").read_text())
        meta.pop("session_id")
        if value:
            meta["session_id"] = value[0]
        (self.out / "run.json").write_text(json.dumps(meta))

    def test_session_comes_from_run_json_before_the_environment(self) -> None:
        """A review outside Claude Code stays session-less even if log runs inside it."""
        self.set_run_session(None)
        self.run_log("log", "--out", str(self.out))
        (run,) = self.records("review_run")
        self.assertNotIn("session_id", run)
        self.assertNotIn("harness", run)

    def test_old_run_json_falls_back_to_the_environment(self) -> None:
        """A run.json written before session capture uses the log-time session."""
        self.set_run_session()
        self.run_log("log", "--out", str(self.out))
        (run,) = self.records("review_run")
        self.assertEqual((run["session_id"], run["harness"]), ("s-env", "claude-code"))

    def test_two_logs_of_one_out_dir_are_byte_identical(self) -> None:
        """Ids and times come from the out dir, so a rerun cannot conflict in hippo."""
        first, second = self.tmp / "a.jsonl", self.tmp / "b.jsonl"
        for ledger, session in ((first, "s-a"), (second, "s-b")):
            with (
                mock.patch.object(self.log, "LEDGER", ledger),
                mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": session}),
            ):
                self.run_log("log", "--out", str(self.out))
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_ids_follow_the_design_recipe(self) -> None:
        """Run id and finding id are the documented hash prefixes."""
        self.run_log("log", "--out", str(self.out))
        (run,) = self.records("review_run")
        (finding,) = self.records("finding")
        input_sha = hashlib.sha256(b"abc").hexdigest()
        self.assertEqual(run["input_sha256"], input_sha)
        run_key = f"{self.repo}|{self.base_sha}|{self.head_sha}|{input_sha}|1792900000000"
        self.assertEqual(run["id"], hashlib.sha256(run_key.encode()).hexdigest()[:16])
        unit_hash = hashlib.sha256(self.unit.encode()).hexdigest()
        finding_key = f"{run['id']}|a.py|{unit_hash}|+2|eval on input"
        self.assertEqual(finding["id"], hashlib.sha256(finding_key.encode()).hexdigest()[:16])

    def test_log_is_idempotent_and_mark_wins(self) -> None:
        """Logging the same run twice adds nothing; the latest human mark is the status."""
        self.run_log("log", "--out", str(self.out))
        self.run_log("log", "--out", str(self.out))
        self.assertEqual(len(agent_eval.read(self.log.LEDGER)), 2)
        self.assertEqual(self.hippo_calls(), 1)  # a rerun writes nothing, so it sends nothing
        fid = self.only_finding()["id"]
        self.run_log("mark", fid, "false-positive")
        self.run_log("mark", fid, "accepted", "--note", "fixed")
        self.assertEqual(self.only_finding()["status"], "accepted")
        verdict = self.records("verdict")[-1]
        self.assertEqual((verdict["auto"], verdict["note"], verdict["finding_id"]), (False, "fixed", fid))
        self.assertNotIn("commit", verdict)

    def test_human_verdict_outranks_a_later_automatic_one(self) -> None:
        """A line-change heuristic must not override a human judgment."""
        self.run_log("log", "--out", str(self.out))
        fid = self.only_finding()["id"]
        agent_eval.append(self.log.LEDGER, [
            {"schema_version": 1, "type": "verdict", "id": "h", "finding_id": fid,
             "verdict": "false-positive", "auto": False, "decided_at": 1},
            {"schema_version": 1, "type": "verdict", "id": "a", "finding_id": fid,
             "verdict": "likely-addressed", "auto": True, "decided_at": 2},
        ])
        self.assertEqual(self.only_finding()["status"], "false-positive")

    def test_mark_commit_resolves_to_full_sha(self) -> None:
        """A short SHA is written as 40 hex; an unknown one is an error and writes nothing."""
        self.run_log("log", "--out", str(self.out))
        fid = self.only_finding()["id"]
        self.run_log("mark", fid, "accepted", "--commit", self.base_sha[:8])
        self.assertEqual(self.records("verdict")[0]["commit"], self.base_sha)
        with self.assertRaises(SystemExit):
            self.run_log("mark", fid, "accepted", "--commit", "0000000")
        self.assertEqual(len(self.records("verdict")), 1)

    def test_escape_commit_resolves_to_full_sha(self) -> None:
        """fix_commit is a full SHA, the repo an absolute path; a bad SHA writes nothing."""
        self.run_log("escape", "--repo", str(self.repo / "."), "--path", "a.py", "--line", "2",
                     "--note", "missed", "--commit", self.base_sha[:8])
        (escape,) = self.records("escape")
        self.assertEqual(escape["fix_commit"], self.base_sha)
        self.assertEqual(escape["repo"], str(self.repo.resolve()))
        with self.assertRaises(SystemExit):
            self.run_log("escape", "--repo", str(self.repo), "--path", "a.py", "--line", "2",
                         "--note", "missed", "--commit", "nope")
        self.assertEqual(len(self.records("escape")), 1)

    def test_ids_depend_on_run_and_reviewed_text(self) -> None:
        """Another repo is another run; new unit text is a new finding in the same run."""
        self.run_log("log", "--out", str(self.out))
        other = self.tmp / "other" / self.out.name
        shutil.copytree(self.out, other)
        manifest = json.loads((other / "manifest.json").read_text())
        manifest["repo"] = str(self.tmp / "repo2")
        (other / "manifest.json").write_text(json.dumps(manifest))
        self.run_log("log", "--out", str(other))
        self.assertEqual(len(self.log.load()[1]), 2)
        (self.out / "units" / "f01.py.diff").write_text("file f01.py\n+2|y = eval(t)\n")
        self.run_log("log", "--out", str(self.out))
        self.assertEqual(len(self.log.load()[1]), 3)
        self.assertEqual(len(self.log.load()[0]), 2)

    def test_removed_line_text_comes_from_the_base_commit(self) -> None:
        """Side "-" cites the line at base_sha, not the working tree."""
        self.write_result(self.finding("-", "int lost"))
        self.run_log("log", "--out", str(self.out))
        self.assertEqual(self.only_finding()["line_text"], "y = int(s)")

    def test_line_text_is_split_at_newlines_only(self) -> None:
        """A form feed inside a source line keeps the whole raw line."""
        (self.repo / "a.py").write_text("x = 1\ny = eval(s)\x0c# z\n")
        self.run_log("log", "--out", str(self.out))
        self.assertEqual(self.only_finding()["line_text"], "y = eval(s)\x0c# z")

    def test_line_text_is_omitted_when_the_source_moved_on(self) -> None:
        """A line edited between review and log must not be stored as the reviewed line."""
        (self.repo / "a.py").write_text("x = 1\ny = exec(s)\n")
        self.run_log("log", "--out", str(self.out))
        self.assertNotIn("line_text", self.only_finding())
        self.assertEqual(len(self.stderr.splitlines()), 1)
        self.assertIn("differs from the reviewed unit", self.stderr)

    def test_unreadable_source_omits_line_text_with_a_warning(self) -> None:
        """A deleted file gives no line text and one warning line, never a silent gap."""
        (self.repo / "a.py").unlink()
        self.run_log("log", "--out", str(self.out))
        self.assertNotIn("line_text", self.only_finding())
        self.assertIn("a.py:+2: source not readable", self.stderr)

    def log_line(self, name: str, unit_row: str, current: str, line: int = 1) -> dict:
        """Log one finding on ``name`` whose unit row is ``unit_row`` while the file holds ``current``."""
        (self.repo / name).write_text(current + "\n")
        manifest = json.loads((self.out / "manifest.json").read_text())
        manifest["files"][0]["path"] = name
        (self.out / "manifest.json").write_text(json.dumps(manifest))
        (self.out / "units" / "f01.py.diff").write_text(f"file f01.py\n+{line}|{unit_row}\n")
        self.write_result({**self.finding(), "line": line})
        self.run_log("log", "--out", str(self.out))
        return self.only_finding()

    def test_appended_code_omits_line_text(self) -> None:
        """Code appended after review is not the reviewed line."""
        found = self.log_line("a.py", "y = eval(s)", "y = eval(s) if trusted else None")
        self.assertNotIn("line_text", found)
        self.assertIn("differs from the reviewed unit", self.stderr)

    def test_code_inserted_into_whitespace_omits_line_text(self) -> None:
        """``x = 1`` and ``x+= 1`` differ only in blanks and still do not match."""
        self.assertNotIn("line_text", self.log_line("a.py", "x = 1", "x+= 1"))

    def test_changed_token_omits_line_text(self) -> None:
        """A token edited inside the line does not match."""
        self.assertNotIn("line_text", self.log_line("a.py", "y = eval(s)", "y = eval(t)"))

    def test_mid_line_comment_keeps_line_text(self) -> None:
        """A blanked mid-line comment still matches and the raw line is stored."""
        raw = "y = f(/* c */ s);"
        self.assertEqual(self.log_line("a.js", "y = f(        s);", raw)["line_text"], raw)

    def test_trailing_comment_added_after_review_keeps_line_text(self) -> None:
        """A comment added after review strips to the reviewed row."""
        raw = "y = eval(s)  # added later"
        self.assertEqual(self.log_line("a.py", "y = eval(s)", raw)["line_text"], raw)

    def test_blank_unit_row_omits_line_text(self) -> None:
        """A finding on a blanked comment-only row must not store whatever line is there now."""
        (self.out / "units" / "f01.py.diff").write_text("file f01.py\n+2|\n")
        self.run_log("log", "--out", str(self.out))
        self.assertNotIn("line_text", self.only_finding())
        self.assertIn("differs from the reviewed unit", self.stderr)

    def test_records_follow_the_v1_contract(self) -> None:
        """Every record type carries its required fields and no field outside section 4.3."""
        self.run_log("log", "--out", str(self.out))
        fid = self.only_finding()["id"]
        self.run_log("mark", fid, "duplicate", "--note", "n", "--commit", self.head_sha[:7])
        self.run_log("escape", "--repo", str(self.repo), "--path", "a.py", "--line", "1",
                     "--note", "missed", "--commit", "HEAD")
        records = agent_eval.read(self.log.LEDGER)
        # bench_run is checked on bench.py output in BenchRecordTest.
        self.assertEqual({r["type"] for r in records}, set(CONTRACT) - {"bench_run"})
        for rec in records:
            with self.subTest(type=rec["type"], id=rec["id"]):
                assert_contract(self, rec)

    def test_automatic_verdict_follows_the_v1_contract(self) -> None:
        """reconcile writes a contract-valid verdict too."""
        self.assertEqual(self.reconcile_status("x = 1\n"), "likely-addressed")
        (verdict,) = self.records("verdict")
        assert_contract(self, verdict)

    def test_failed_review_is_recorded_as_failed_not_clean(self) -> None:
        """A failed unit gives a run with units_failed, no findings, and exit 1."""
        (self.out / "results" / "f01.py.json").write_text(
            json.dumps({"unit": "f01.py", "ok": False, "error": "api down", "findings": []})
        )
        self.assertEqual(self.run_log("log", "--out", str(self.out)), 1)
        self.assertEqual(self.log.load()[1], {})
        self.assertEqual(self.records("review_run")[0]["units_failed"], 1)

    def test_missing_result_is_reported_not_logged_as_clean(self) -> None:
        """An interrupted review leaves no result file; that must not read as 0 findings."""
        (self.out / "results" / "f01.py.json").unlink()
        self.assertEqual(self.run_log("log", "--out", str(self.out)), 1)
        self.assertEqual(self.records("review_run")[0]["units_failed"], 1)

    def test_missing_run_json_is_an_error(self) -> None:
        """Without run.json the run has no SHAs or times, so nothing is logged."""
        (self.out / "run.json").unlink()
        self.assertEqual(self.run_log("log", "--out", str(self.out)), 1)
        self.assertFalse(self.log.LEDGER.exists())

    def test_duplicate_findings_in_one_run_log_once(self) -> None:
        """Two identical findings in one result are one finding."""
        self.write_result(self.finding(), self.finding())
        self.run_log("log", "--out", str(self.out))
        self.assertEqual(len(self.records("finding")), 1)

    def test_torn_ledger_line_is_skipped(self) -> None:
        """A write cut short must not make every later command fail."""
        self.run_log("log", "--out", str(self.out))
        with self.log.LEDGER.open("a") as fh:
            fh.write('{"schema_version":1,"type":"fin')
        fid = self.only_finding()["id"]
        self.run_log("mark", fid, "accepted")
        self.assertEqual(self.only_finding()["status"], "accepted")

    def test_escape_on_a_pre_v1_ledger_moves_it_first(self) -> None:
        """escape writes no v1 record into an old-format file, so no mixed ledger arises."""
        old = '{"type": "escape", "at": "2026-01-01T00:00:00+00:00", "note": "x"}\n'
        self.log.LEDGER.write_text(old)
        self.run_log("escape", "--repo", str(self.repo), "--path", "a.py", "--line", "1",
                     "--note", "missed")
        self.assertEqual(self.log.LEDGER.with_name("l.legacy.jsonl").read_text(), old)
        (escape,) = agent_eval.read(self.log.LEDGER)
        assert_contract(self, escape)

    def test_stray_pre_v1_line_in_a_v1_ledger_is_skipped_not_moved(self) -> None:
        """One old line must not move the v1 records or block every command."""
        self.run_log("log", "--out", str(self.out))
        before = self.log.LEDGER.read_text()
        with self.log.LEDGER.open("a") as fh:
            fh.write('{"type": "status", "id": "abc"}\n')
        self.log.LEDGER.with_name("l.legacy.jsonl").write_text("old\n")
        self.assertEqual(self.run_log("summary"), 0)
        self.assertEqual(self.stderr.count("pre-v1"), 1)
        self.assertTrue(self.log.LEDGER.read_text().startswith(before))
        self.assertEqual(len(self.log.load()[1]), 1)

    def test_legacy_ledger_is_moved_aside_without_loss(self) -> None:
        """Pre-v1 events cannot become v1 records; they are kept byte for byte."""
        old = '{"type": "finding", "id": "abc", "claim": "x"}\n{"type": "status", "id": "abc"}\n'
        self.log.LEDGER.write_text(old)
        self.run_log("log", "--out", str(self.out))
        legacy = self.log.LEDGER.with_name("l.legacy.jsonl")
        self.assertEqual(legacy.read_text(), old)
        self.assertTrue(all(r["schema_version"] == 1 for r in agent_eval.read(self.log.LEDGER)))

    def reconcile_status(self, source: str) -> str:
        """Log the run, rewrite a.py to ``source``, reconcile, and return the status."""
        self.run_log("log", "--out", str(self.out))
        (self.repo / "a.py").write_text(source)
        self.run_log("reconcile")
        return self.only_finding()["status"]

    def test_reconcile_marks_a_changed_line_likely_addressed(self) -> None:
        """A rewritten flagged line gets an automatic likely-addressed verdict."""
        self.assertEqual(self.reconcile_status("x = 1\ny = int(s)\n"), "likely-addressed")
        (verdict,) = self.records("verdict")
        self.assertIs(verdict["auto"], True)
        self.assertRegex(verdict["id"], r"^[0-9a-f-]{36}$")

    def test_reconcile_keeps_an_unchanged_line_open(self) -> None:
        """An untouched flagged line writes no verdict and sends nothing to hippo."""
        self.assertEqual(self.reconcile_status("x = 1\ny = eval(s)\n"), "open")
        self.assertEqual(self.records("verdict"), [])
        self.assertEqual(self.hippo_calls(), 1)  # only the log write

    def test_reconcile_keeps_a_moved_but_unchanged_line_open(self) -> None:
        """Imports added above the flagged line move it; that is not a fix."""
        moved = "import a\nimport b\nimport c\nx = 1\n    y = eval(s)\r\n"
        self.assertEqual(self.reconcile_status(moved), "open")

    def test_reconcile_compares_raw_lines_with_their_comments(self) -> None:
        """A flagged line with a trailing comment stays open while the raw line is unchanged."""
        (self.repo / "a.py").write_text("x = 1\ny = eval(s)  # safe\n")
        self.assertEqual(self.reconcile_status("x = 1\ny = eval(s)  # safe\n"), "open")
        self.assertEqual(self.only_finding()["line_text"], "y = eval(s)  # safe")

    def test_reconcile_skips_a_finding_with_a_human_verdict(self) -> None:
        """A judged finding is not open, so the heuristic adds nothing."""
        self.run_log("log", "--out", str(self.out))
        self.run_log("mark", self.only_finding()["id"], "false-positive")
        (self.repo / "a.py").write_text("x = 1\n")
        self.run_log("reconcile")
        self.assertEqual(len(self.records("verdict")), 1)


class MechanicalRunTest(unittest.TestCase):
    """mechanical_review.py must record the run facts and refuse unresolvable commits."""

    def setUp(self) -> None:
        """Build a repo with one commit and an out dir with one unit; stub the reviewer."""
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        isolate_path(self, self.tmp)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        bench.git(self.repo, "init", "-q", "-b", "main")
        self.out = self.tmp / "out"
        (self.out / "units").mkdir(parents=True)
        (self.out / "units" / "f01.py.diff").write_text("file f01.py\n+1|x = 1\n")
        (self.out / "units" / "f02.py.diff").write_text("file f02.py\n+1|y = 1\n")
        usage = {"input_tokens": 5, "output_tokens": 2, "cache_read_input_tokens": 7,
                 "cache_creation_input_tokens": 1, "service_tier": "standard"}
        self.review = mock.Mock(side_effect=lambda unit, *_: {
            "unit": unit.stem, "ok": True, "findings": [], "usage": usage, "error": None})
        for patcher in (
            mock.patch.object(mechanical_review, "review_unit", self.review),
            mock.patch.object(mechanical_review, "SANDBOX", self.tmp / "sandbox"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def main(self, base: str) -> int:
        """Write the manifest for ``base`` and run the reviewer fan-out."""
        (self.out / "manifest.json").write_text(json.dumps(
            {"repo": str(self.repo), "base": base, "mode": "mechanical", "files": []}))
        with mock.patch("sys.stdout", new=io.StringIO()), mock.patch("sys.stderr", new=io.StringIO()):
            return mechanical_review.main(["--out", str(self.out), "--model", "haiku", "--effort", "low"])

    def test_refuses_a_repo_without_commits(self) -> None:
        """No HEAD means no head_sha: nothing is reviewed and no run.json is written."""
        self.assertEqual(self.main("HEAD"), 1)
        self.review.assert_not_called()
        self.assertFalse((self.out / "run.json").exists())

    def test_refuses_an_unresolvable_base_and_drops_a_stale_run_json(self) -> None:
        """A bad base ref stops the run; an old run.json must not survive it."""
        (self.repo / "a").write_text("a\n")
        commit_all(self.repo, "a")
        (self.out / "run.json").write_text("{}")
        self.assertEqual(self.main("no-such-ref"), 1)
        self.review.assert_not_called()
        self.assertFalse((self.out / "run.json").exists())

    def test_run_json_holds_the_design_fields(self) -> None:
        """Times, model, effort, base, both SHAs, and summed reviewer tokens."""
        (self.repo / "a").write_text("a\n")
        base = commit_all(self.repo, "a")
        (self.repo / "a").write_text("b\n")
        head = commit_all(self.repo, "b")
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "s-review"}):
            self.assertEqual(self.main("HEAD~1"), 0)
        run = json.loads((self.out / "run.json").read_text())
        self.assertLessEqual(run.pop("started_at"), run.pop("finished_at"))
        self.assertEqual(run, {
            "requested_model": "haiku", "effort": "low", "base": "HEAD~1",
            "base_sha": base, "head_sha": head, "session_id": "s-review",
            "input_tokens": 10, "output_tokens": 4,
            "cache_read_tokens": 14, "cache_creation_tokens": 2,
        })


class BenchRecordTest(unittest.TestCase):
    """bench.py run --record must append a v1 bench_run with a content id and ingest it."""

    def test_record_appends_v1_bench_run_and_ingests(self) -> None:
        """The record id is the hash of the record without it; hippo gets the file."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        calls = isolate_path(self, tmp)
        results = tmp / "results.jsonl"
        ok = {"ok": True, "findings": [], "usage": {"input_tokens": 3}, "model_id": "m-1",
              "input_sha256": "x", "error": None}
        with (
            mock.patch.object(bench.mechanical_review, "review_unit", return_value=ok),
            mock.patch.object(bench.mechanical_review, "cli_version", return_value="t"),
            mock.patch.object(bench, "RESULTS", results),
            mock.patch.object(bench, "_commit", return_value="abc1234"),
            mock.patch("sys.stdout", new=io.StringIO()),
            mock.patch("sys.stderr", new=io.StringIO()),
        ):
            code = bench.main(["run", "--reps", "1", "--case", "c01-py-path-guard-removed", "--record"])
        self.assertEqual(code, 0)
        (record,) = agent_eval.read(results)
        self.assertEqual((record["schema_version"], record["type"], record["bench"]),
                         (1, "bench_run", "blind-review-mechanical"))
        self.assertIsInstance(record["recorded_at"], int)
        self.assertEqual(record["model_ids"], ["m-1"])
        assert_contract(self, record)
        body = json.dumps({k: v for k, v in record.items() if k != "id"},
                          sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.assertEqual(record["id"], hashlib.sha256(body.encode()).hexdigest()[:16])
        self.assertEqual(calls.read_text(), f"ingest agent-eval {results}\n")

    def test_committed_history_is_v1_with_valid_ids(self) -> None:
        """The recorded runs were rewritten once into v1 records with recomputable ids."""
        rows = agent_eval.read(bench.RESULTS)
        self.assertGreaterEqual(len(rows), 2)
        for row in rows:
            self.assertEqual((row["schema_version"], row["type"]), (1, "bench_run"))
            self.assertEqual(row["id"], bench.bench_run_id(row))


PRIVATE_FILE = "src/pkg/auth.py"
PRIVATE_CASE = {
    "id": "f-0123456789abcdef",
    "description": "Accepted finding 0123456789abcdef: the change reintroduces the flagged line.",
    "base": {PRIVATE_FILE: "def check(user):\n    if user.is_admin:\n        return True\n    return False\n"},
    "head": {PRIVATE_FILE: "def check(user):\n    if user.is_admin or True:\n        return True\n    return False\n"},
    "traps": [{"id": "defect", "kind": "bug", "category": "logic", "severity": "high",
               "path": PRIVATE_FILE, "anchors": [["+", 2]], "why": "The or True bypasses the check."}],
}


class PrivateCorpusTest(unittest.TestCase):
    """``run --cases-dir`` must score a private corpus and keep it out of results.jsonl."""

    def setUp(self) -> None:
        """Write the private case to a temp corpus and isolate PATH and the public results."""
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cases = self.tmp / "corpus"
        self.cases.mkdir()
        (self.cases / f"{PRIVATE_CASE['id']}.json").write_text(json.dumps(PRIVATE_CASE))
        self.calls = isolate_path(self, self.tmp)
        self.public = self.tmp / "public-results.jsonl"

    def run_bench(self, *argv: str) -> int:
        """Run bench.py with a reviewer that reports nothing."""
        ok = {"ok": True, "findings": [], "usage": {"input_tokens": 3}, "model_id": "m-1",
              "input_sha256": "x", "error": None}
        with (
            mock.patch.object(bench.mechanical_review, "review_unit", return_value=ok),
            mock.patch.object(bench.mechanical_review, "cli_version", return_value="t"),
            mock.patch.object(bench, "RESULTS", self.public),
            mock.patch.object(bench, "_commit", return_value="abc1234"),
            mock.patch("sys.stdout", new=io.StringIO()),
            mock.patch("sys.stderr", new=io.StringIO()) as stderr,
        ):
            try:
                return bench.main(["run", "--reps", "1", "--cases-dir", str(self.cases), *argv])
            finally:
                self.stderr = stderr.getvalue()

    def test_private_run_is_tagged_and_recorded_outside_the_public_results(self) -> None:
        """The record goes to --results with the private bench tag, and hippo gets that file."""
        results = self.tmp / "private.jsonl"
        self.assertEqual(self.run_bench("--record", "--results", str(results)), 0)
        self.assertFalse(self.public.exists())
        (record,) = agent_eval.read(results)
        assert_contract(self, record)
        self.assertEqual(record["bench"], "blind-review-private")
        self.assertEqual(record["cases"], 1)
        self.assertEqual(record["scores"]["recall"], 0.0)
        self.assertEqual(record["per_case"][0]["case"], PRIVATE_CASE["id"])
        self.assertEqual(self.calls.read_text(), f"ingest agent-eval {results}\n")

    def test_default_private_results_path(self) -> None:
        """Without --results a private run records under the XDG data directory."""
        data = self.tmp / "data"
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(data)}):
            self.assertEqual(self.run_bench("--record"), 0)
        self.assertEqual(len(agent_eval.read(data / "blind-review/private-results.jsonl")), 1)
        self.assertFalse(self.public.exists())

    def test_public_results_file_is_refused_for_a_private_corpus(self) -> None:
        """Naming results.jsonl explicitly must not leak private case ids into the repo."""
        with self.assertRaises(SystemExit):
            self.run_bench("--record", "--results", str(self.public))
        self.assertFalse(self.public.exists())

    def test_case_path_outside_the_fixture_repo_is_refused(self) -> None:
        """A case file is data; its paths must not write outside the fixture repo."""
        case = {**PRIVATE_CASE, "base": {"../escape.py": "x\n"}}
        with self.assertRaises(SystemExit):
            bench.build_units(case, self.tmp / "build")
        self.assertFalse((self.tmp / "build/escape.py").exists())
        target = self.tmp / "abs.py"
        with self.assertRaises(SystemExit):
            bench.build_units({**PRIVATE_CASE, "base": {str(target): "x\n"}}, self.tmp / "abs")
        self.assertFalse(target.exists())

    def test_private_case_without_an_anchor_row_is_skipped(self) -> None:
        """A regenerated private case must not abort the run or count in the scores."""
        bad = {**PRIVATE_CASE, "id": "e-unanchored",
               "traps": [{**PRIVATE_CASE["traps"][0], "anchors": [["+", 4]]}]}
        (self.cases / "e-unanchored.json").write_text(json.dumps(bad))
        results = self.tmp / "private.jsonl"
        self.assertEqual(self.run_bench("--record", "--results", str(results)), 0)
        self.assertIn("skipped e-unanchored: no anchor is a row of its unit", self.stderr)
        (record,) = agent_eval.read(results)
        assert_contract(self, record)
        self.assertEqual(record["cases"], 1)
        only_good = hashlib.sha256(json.dumps([PRIVATE_CASE], sort_keys=True).encode()).hexdigest()[:12]
        self.assertEqual(record["cases_sha256"], only_good)
        self.assertEqual(record["per_case"][-1],
                         {"case": "e-unanchored", "reps": 0, "skipped": "no anchor is a row of its unit"})

    def test_public_case_without_an_anchor_row_still_aborts(self) -> None:
        """A hand-written public case with a wrong anchor must be fixed, not skipped."""
        bad = {**PRIVATE_CASE, "traps": [{**PRIVATE_CASE["traps"][0], "anchors": [["+", 4]]}]}
        with (
            mock.patch.object(bench, "load_cases", return_value=[bad]),
            mock.patch("sys.stdout", new=io.StringIO()),
            self.assertRaises(bench.AnchorMissing),
        ):
            bench.main(["run", "--reps", "1"])

    def test_private_run_removes_its_temp_dir(self) -> None:
        """Private file text and raw reviewer output must not stay in the temp dir."""
        root = self.tmp / "bench-root"
        root.mkdir()
        with mock.patch.object(bench.tempfile, "mkdtemp", return_value=str(root)):
            self.assertEqual(self.run_bench("--results", str(self.tmp / "p.jsonl")), 0)
        self.assertFalse(root.exists())


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

    def test_result_symlink_is_not_written_through(self) -> None:
        """A leftover result link must not let a rerun overwrite the file it points at."""
        with tempfile.TemporaryDirectory() as tmp:
            out, target = Path(tmp) / "out", Path(tmp) / "source.py"
            target.write_text("keep\n")
            for sub in ("units", "payloads", "results"):
                (out / sub).mkdir(parents=True)
            unit = out / "units" / "f01.py.diff"
            unit.write_text("file f01.py\n+1|x = 1\n")
            (out / "results" / "f01.py.json").symlink_to(target)
            (out / "payloads" / "f01.py.json").symlink_to(target)
            fake = [sys.executable, "-c", "print('{}')"]
            mechanical_review.review_unit(unit, out, fake, "no-such-repo-name")
            self.assertEqual(target.read_text(), "keep\n")

    def test_refuses_symlinked_sandbox(self) -> None:
        """On a shared /tmp another user could point the path at their own directory."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "elsewhere"
            target.mkdir()
            box = Path(tmp) / "blind-review-sandbox"
            box.symlink_to(target)
            with mock.patch.object(mechanical_review, "SANDBOX", box), self.assertRaises(SystemExit):
                mechanical_review.sandbox("repo-x")


if __name__ == "__main__":
    unittest.main()
