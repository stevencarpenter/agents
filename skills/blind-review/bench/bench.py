#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "tree-sitter==0.25.2",
#     "tree-sitter-python==0.25.0",
#     "tree-sitter-c==0.24.2",
#     "tree-sitter-java==0.23.5",
#     "tree-sitter-kotlin==1.1.0",
#     "tree-sitter-scala==0.26.2",
#     "tree-sitter-swift==0.7.4",
#     "tree-sitter-groovy==0.1.2",
#     "tree-sitter-go==0.25.0",
#     "tree-sitter-rust==0.24.2",
#     "tree-sitter-javascript==0.25.0",
#     "tree-sitter-typescript==0.23.2",
#     "tree-sitter-css==0.25.0",
#     "tree-sitter-json==0.24.8",
#     "tree-sitter-bash==0.25.1",
#     "tree-sitter-make==1.1.1",
#     "tree-sitter-dockerfile==0.2.0",
#     "tree-sitter-toml==0.7.0",
#     "tree-sitter-yaml==0.7.2",
#     "tree-sitter-hcl==1.2.0",
#     "tree-sitter-nix==0.1.0",
#     "tree-sitter-ruby==0.23.1",
#     "tree-sitter-lua==0.5.0",
#     "tree-sitter-sql==0.3.11",
#     "tree-sitter-html==0.23.2",
#     "tree-sitter-xml==0.7.0",
# ]
# ///
"""bench.py: score mechanical blind review against cases with known defects.

Each case in ``cases/`` gives base and head file contents and traps: a ``bug``
trap is a planted defect a reviewer should report, a ``safe`` trap is correct
code that looks suspicious. A trap is hit when a finding has the same file and
side and a line within 1 of one of its anchors. Findings are structured, so no
judge model is needed.

Every case runs ``--reps`` times. Scores:
  recall           bug traps hit / bug traps (context-required traps apart)
  safe_false_alarm medium or high findings on safe traps / safe trap runs
  extra_findings   findings that match no trap, per run
  trap_stability   traps with the same outcome in every rep / traps
  finding_jaccard  mean pairwise overlap of (unit, side, line) sets across reps
  input_identical  every rep sent byte-identical input for every unit

``run --record`` appends an agent-eval v1 ``bench_run`` record (the scores, the
repo commit, the CLI version, and the resolved model ID) to ``results.jsonl``,
then hands the file to ``hippo ingest agent-eval`` when ``hippo`` is on PATH.
The record ``id`` is the first 16 hex characters of the SHA-256 of the
record's canonical JSON without ``id``. ``summary`` prints that history.

``run --cases-dir DIR`` runs a private corpus (for example the output of
``hippo eval export-bench-cases``) instead of ``cases/``. Its records carry
``bench: blind-review-private`` and go to ``--results`` (default
``$XDG_DATA_HOME/blind-review/private-results.jsonl``), never to the public
``results.jsonl``.

Usage: bench.py run [--model sonnet] [--effort high] [--reps 3] [--jobs 4]
                    [--case ID]... [--cases-dir DIR] [--results PATH] [--record]
       bench.py summary [--results PATH]
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import itertools
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
RESULTS = HERE / "results.jsonl"
sys.path.insert(0, str(SCRIPTS))
import agent_eval
import mechanical_review
import strip_context

BENCH = "blind-review-mechanical"
PRIVATE_BENCH = "blind-review-private"


def private_results() -> Path:
    """Return the default results file for private-corpus runs."""
    data = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share"
    return Path(data) / "blind-review" / "private-results.jsonl"


def bench_run_id(record: dict) -> str:
    """Return the record id: a hash of the canonical record JSON without ``id``."""
    body = {k: v for k, v in record.items() if k != "id"}
    return agent_eval.short_hash(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def load_cases(ids: list[str] | None = None, cases_dir: Path | None = None) -> list[dict]:
    """Load cases from ``cases_dir`` (default ``cases/``), optionally only the named IDs."""
    paths = sorted((cases_dir or HERE / "cases").glob("*.json"))
    cases = [json.loads(p.read_text()) for p in paths]
    return [c for c in cases if not ids or c["id"] in ids]


def git(repo: Path, *args: str) -> None:
    """Run git in a fixture repo with a fixed identity and no user config.

    A global ``commit.gpgsign`` or ``core.hooksPath`` would make the fixture
    commit fail or prompt.
    """
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=b@example.com", "-c", "user.name=b", *args],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"},
    )


def build_units(case: dict, root: Path) -> tuple[Path, dict[str, str]]:
    """Create the case repo, run the mechanical strip, return (out dir, path->unit)."""
    repo = root / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    def write(rel: str, text: str) -> None:
        # Private cases carry real repo paths: keep them inside the fixture repo.
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise SystemExit(f"{case['id']}: unsafe path {rel!r}")
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)

    for rel, text in case["base"].items():
        write(rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    for rel, text in case["head"].items():
        write(rel, text)
    out = root / "out"
    strip_context.main(["mechanical", "--repo", str(repo), "--out", str(out)])
    manifest = json.loads((out / "manifest.json").read_text())
    units = {f["path"]: f["unit"] for f in manifest["files"] if "unit" in f}
    for trap in case["traps"]:
        unit = units.get(trap["path"])
        rows = (out / "units" / f"{unit}.diff").read_text() if unit else ""
        if not any(f"\n{side}{line}|" in rows for side, line in trap["anchors"]):
            raise SystemExit(f"{case['id']}/{trap['id']}: no anchor is a row of its unit")
    return out, units


def matches(finding: dict, unit: str, trap: dict, units: dict[str, str]) -> bool:
    """Report whether a finding in ``unit`` lands on one of the trap's anchors."""
    if units.get(trap["path"]) != unit:
        return False
    return any(
        finding.get("side") == side and abs(int(finding.get("line", -99)) - line) <= 1
        for side, line in trap["anchors"]
    )


def score_rep(case: dict, units: dict[str, str], results: dict[str, dict]) -> dict:
    """Score one rep of one case: trap outcomes and unmatched findings."""
    outcome: dict[str, bool] = {}
    matched: set[tuple[str, int]] = set()
    for trap in case["traps"]:
        hit = False
        for unit, result in results.items():
            for i, finding in enumerate(result["findings"]):
                if not matches(finding, unit, trap, units):
                    continue
                matched.add((unit, i))
                if trap["kind"] == "bug" or finding.get("severity") in ("high", "medium"):
                    hit = True
        outcome[trap["id"]] = hit
    extra = sum(
        (unit, i) not in matched
        for unit, result in results.items()
        for i in range(len(result["findings"]))
    )
    return {"outcome": outcome, "extra": extra}


def jaccard(sets: list[set]) -> float:
    """Mean pairwise Jaccard similarity; 1.0 when every set is empty."""
    pairs = list(itertools.combinations(sets, 2))
    if not pairs:
        return 1.0
    return sum(len(a & b) / len(a | b) if a | b else 1.0 for a, b in pairs) / len(pairs)


def run(args: argparse.Namespace) -> int:
    """Run every case ``--reps`` times, print the scores, and optionally record them."""
    results_path = args.results or (private_results() if args.cases_dir else RESULTS)
    if args.cases_dir and results_path.resolve() == RESULTS.resolve():
        raise SystemExit(f"a private corpus must not be recorded in {RESULTS}")
    cases = load_cases(args.case, args.cases_dir)
    missing = set(args.case or ()) - {c["id"] for c in cases}
    if missing or not cases:
        raise SystemExit(f"no such case: {', '.join(sorted(missing)) or '(none loaded)'}")
    cmd = mechanical_review.reviewer_argv(args.model, args.effort)
    root = Path(tempfile.mkdtemp(prefix="bench-"))
    built = {c["id"]: build_units(c, root / c["id"]) for c in cases}
    jobs = [
        (c["id"], rep, unit_file)
        for c in cases
        for rep in range(args.reps)
        for unit_file in sorted((built[c["id"]][0] / "units").glob("*.diff"))
    ]

    def review(job: tuple[str, int, Path]) -> tuple[str, int, str, dict]:
        case_id, rep, unit_file = job
        rep_dir = root / case_id / f"rep{rep}"
        for sub in ("payloads", "results"):
            (rep_dir / sub).mkdir(parents=True, exist_ok=True)
        # Fixture repo names never collide with the sandbox path.
        result = mechanical_review.review_unit(unit_file, rep_dir, cmd, "repo-not-named")
        return case_id, rep, unit_file.stem, result

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        reviews = list(pool.map(review, jobs))

    failed = [f"{c}/rep{r}/{u}: {res['error']}" for c, r, u, res in reviews if not res["ok"]]
    per_case = []
    totals = {"bug": 0, "bug_hit": 0, "ctx": 0, "ctx_hit": 0, "safe": 0, "safe_fa": 0}
    extras, stable, trap_count, jaccards, input_ok, tokens = 0, 0, 0, [], True, 0
    model_ids = sorted({res["model_id"] for *_, res in reviews if res["model_id"]})
    for case in cases:
        units = built[case["id"]][1]
        # A rep with a failed unit is left out: its missing results would score as "no findings".
        by_rep = []
        for rep in range(args.reps):
            mine = {u: res for c, r, u, res in reviews if c == case["id"] and r == rep}
            if all(res["ok"] for res in mine.values()):
                by_rep.append(mine)
        reps = [score_rep(case, units, results) for results in by_rep]
        hits = {t["id"]: sum(r["outcome"][t["id"]] for r in reps) for t in case["traps"]}
        for trap in case["traps"]:
            key = "safe" if trap["kind"] == "safe" else "ctx" if trap.get("context_required") else "bug"
            totals[key] += len(reps)
            totals[{"safe": "safe_fa", "ctx": "ctx_hit", "bug": "bug_hit"}[key]] += hits[trap["id"]]
            if reps:  # with no scored rep, stability is unknown, not perfect
                trap_count += 1
                stable += hits[trap["id"]] in (0, len(reps))
        extras += sum(r["extra"] for r in reps)
        for unit in units.values():
            sets = [
                {(f["side"], f["line"]) for f in results[unit]["findings"]}
                for results in by_rep
                if unit in results
            ]
            if sets:
                jaccards.append(jaccard(sets))
            hashes = {res["input_sha256"] for c, _, u, res in reviews if c == case["id"] and u == unit}
            input_ok &= len(hashes) == 1
        tokens += sum(
            sum((res.get("usage") or {}).get(k, 0) for k in ("input_tokens", "output_tokens",
                "cache_creation_input_tokens", "cache_read_input_tokens"))
            for c, *_, res in reviews if c == case["id"]
        )
        per_case.append({"case": case["id"], "reps": len(reps), "trap_hits": hits,
                         "extra": sum(r["extra"] for r in reps)})

    def rate(num: int, den: int) -> float | None:
        return round(num / den, 3) if den else None

    runs = sum(row["reps"] for row in per_case)
    scores = {
        "recall": rate(totals["bug_hit"], totals["bug"]),
        "context_required_recall": rate(totals["ctx_hit"], totals["ctx"]),
        "safe_false_alarm": rate(totals["safe_fa"], totals["safe"]),
        "extra_findings_per_run": rate(extras, runs),
        "trap_stability": rate(stable, trap_count),
        "finding_jaccard": round(sum(jaccards) / len(jaccards), 3) if jaccards else None,
        "input_identical": input_ok,
    }
    record = {
        "schema_version": agent_eval.SCHEMA_VERSION,
        "type": "bench_run",
        "bench": PRIVATE_BENCH if args.cases_dir else BENCH,
        "recorded_at": agent_eval.now_ms(),
        "repo_commit": _commit(),
        "cli_version": mechanical_review.cli_version(),
        "model": args.model,
        "model_ids": model_ids,
        "effort": args.effort,
        "reps": args.reps,
        "brief_sha256": hashlib.sha256(mechanical_review.BRIEF.encode()).hexdigest()[:12],
        # A corpus edit changes what the scores mean, so it must show in the history.
        "cases_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest()[:12],
        "cases": len(cases),
        "failed_reviews": len(failed),
        "tokens": tokens,
        "scores": scores,
        "per_case": per_case,
    }
    record = {"id": bench_run_id(record)} | record
    print(json.dumps({k: record[k] for k in record if k != "per_case"}, indent=2))
    for row in per_case:
        print(f"  {row['case']}: hits {row['trap_hits']} of {row['reps']}, extra {row['extra']}")
    for line in failed:
        print(f"FAILED {line}", file=sys.stderr)
    print(f"raw output in {root}")
    if args.record and failed:
        print(f"not recorded: {len(failed)} review(s) failed", file=sys.stderr)
    elif args.record:
        results_path.parent.mkdir(parents=True, exist_ok=True)
        agent_eval.append(results_path, [record])
        print(f"recorded -> {results_path}")
        agent_eval.ingest(results_path)
    return 1 if failed else 0


def _commit() -> str:
    """Return the repo commit, marked ``-dirty`` when the bench inputs have edits."""
    def out(*a: str) -> str:
        return subprocess.run(
            ["git", "-C", str(HERE), *a], capture_output=True, text=True, check=False
        ).stdout
    # results.jsonl is output, not input: a concurrent run appending to it is not an edit.
    dirty = out("status", "--porcelain", "--", str(HERE.parent), ":!results.jsonl").strip()
    return out("rev-parse", "--short", "HEAD").strip() + ("-dirty" if dirty else "")


def summary(args: argparse.Namespace) -> int:
    """Print the recorded score history, oldest first."""
    results_path = args.results or RESULTS
    if not results_path.exists():
        print("no recorded runs")
        return 0
    cols = ("recall", "context_required_recall", "safe_false_alarm", "extra_findings_per_run",
            "trap_stability", "finding_jaccard", "input_identical")
    print("recorded_at | commit | cases | model | effort | reps | " + " | ".join(cols))
    for r in agent_eval.read(results_path):
        if r.get("type") != "bench_run":
            continue
        model = ",".join(r["model_ids"]) or r["model"]
        values = " | ".join(str(r["scores"][c]) for c in cols)
        at = datetime.datetime.fromtimestamp(r["recorded_at"] / 1000, datetime.UTC)
        print(
            f"{at.isoformat(timespec='seconds')} | {r['repo_commit']} | {r.get('cases_sha256', '?')} | {model} | "
            f"{r['effort']} | {r['reps']} | {values}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested subcommand."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--model", default="sonnet")
    r.add_argument("--effort", default="high")
    r.add_argument("--reps", type=int, default=3)
    r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--case", action="append")
    r.add_argument("--record", action="store_true")
    r.add_argument("--cases-dir", type=Path, help="private corpus directory instead of cases/")
    r.add_argument("--results", type=Path, help="results file (private default: see above)")
    r.set_defaults(func=run)
    s = sub.add_parser("summary")
    s.add_argument("--results", type=Path)
    s.set_defaults(func=summary)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
