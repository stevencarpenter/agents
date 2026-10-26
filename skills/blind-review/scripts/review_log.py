#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""review_log.py: track whether real mechanical-review findings were useful.

The benchmark (``bench/bench.py``) scores the reviewer on planted defects.
This ledger measures usefulness on real changes: what happened to each
finding, and which defects reviews missed. It is an append-only JSONL file of
agent-eval v1 records (``review_run``, ``finding``, ``verdict``, ``escape``)
at ``~/.local/share/blind-review/findings.jsonl``, local because it holds
private repo paths and code lines. After every write, when ``hippo`` is on
PATH, the whole ledger goes to ``hippo ingest agent-eval``; hippo skips the
ids it already holds. A ledger in the older event format is moved aside to
``findings.legacy.jsonl`` once, unchanged.

A finding's status is its effective verdict: the latest human verdict, else
the latest automatic one, else open.

Subcommands:
  log --out DIR            record the run (from run.json) and every finding of
                           a mechanical out dir
  mark ID STATUS [--note TEXT] [--commit REV]
                           STATUS: accepted (the code changed because of it),
                           false-positive, not-useful, duplicate
  reconcile                mark open "+" findings likely-addressed when the
                           flagged raw line is no longer anywhere in the file
  escape --repo R --path P --line N --note TEXT [--commit REV]
                           record a defect found later that no review reported
  summary                  usefulness rates overall, by category, and by model
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent_eval

LEDGER = Path(
    os.environ.get("BLIND_REVIEW_LEDGER", Path.home() / ".local/share/blind-review/findings.jsonl")
)
STATUSES = ("accepted", "false-positive", "not-useful", "duplicate")
USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")


def record(kind: str, record_id: str, **fields: object) -> dict:
    """Build a v1 record; fields set to None are optional and left out."""
    head = {"schema_version": agent_eval.SCHEMA_VERSION, "type": kind, "id": record_id}
    return head | {k: v for k, v in fields.items() if v is not None}


def retire_legacy_ledger() -> None:
    """Move a ledger that holds only pre-v1 events aside once, keeping every row.

    The old events carry no commit SHAs or run times, so they cannot become
    valid v1 records; they stay readable in ``<stem>.legacy.jsonl``. A ledger
    that already holds v1 records stays in place; ``load`` skips any pre-v1
    line in it.
    """
    records = agent_eval.read(LEDGER)
    if not records or any("schema_version" in r for r in records):
        return
    legacy = LEDGER.with_name(f"{LEDGER.stem}.legacy{LEDGER.suffix}")
    if legacy.exists():
        raise SystemExit(f"{LEDGER} holds pre-v1 events and {legacy} exists; merge them by hand")
    LEDGER.rename(legacy)
    print(f"moved the pre-v1 ledger to {legacy}", file=sys.stderr)


def load() -> tuple[dict[str, dict], dict[str, dict], list[dict]]:
    """Return (runs by id, findings by id with their effective status, escapes)."""
    retire_legacy_ledger()
    runs: dict[str, dict] = {}
    findings: dict[str, dict] = {}
    escapes: list[dict] = []
    verdicts: dict[str, list[dict]] = collections.defaultdict(list)
    records = agent_eval.read(LEDGER)
    if skipped := sum("schema_version" not in r for r in records):
        print(f"warning: {LEDGER} holds {skipped} pre-v1 line(s); skipped", file=sys.stderr)
    for r in records:
        if "schema_version" not in r:
            continue
        match r.get("type"):
            case "review_run":
                runs[r["id"]] = r
            case "finding":
                findings[r["id"]] = {**r, "status": "open"}
            case "verdict":
                verdicts[r["finding_id"]].append(r)
            case "escape":
                escapes.append(r)
    for fid, group in verdicts.items():
        if fid in findings:
            # A human judgment outranks the line-change heuristic.
            latest = max(group, key=lambda v: (not v["auto"], v["decided_at"], v["id"]))
            findings[fid]["status"] = latest["verdict"]
    return runs, findings, escapes


def write(records: list[dict]) -> None:
    """Append records to the ledger, then hand the whole ledger to hippo."""
    agent_eval.append(LEDGER, records)
    agent_eval.ingest(LEDGER)


def masks(row: str, raw: str) -> bool:
    """Report whether a unit row is the space-masked form of ``raw``.

    The stripper blanks comments column for column and trims trailing spaces,
    so every non-space character of the row sits at the same column of the
    raw line. A plain substring test would reject a line with a mid-line
    comment. A blank row (a comment-only or empty line) proves nothing about
    the raw line, so it never matches.
    """
    return bool(row.strip()) and len(row) <= len(raw) and all(c == " " or c == raw[i] for i, c in enumerate(row))


def source_line(repo: str, path: str, side: str, line: int, base_sha: str, row: str | None) -> str | None:
    """Return the raw source line a finding cites, or None with one warning.

    Side ``+`` is the working-tree line (the reviewed tree includes
    uncommitted changes); side ``-`` is the line at ``base_sha``. The line
    must still match the reviewed unit ``row``: a file edited between the
    review and ``log`` gives no line text rather than the wrong one.
    """
    where = f"{path}:{side}{line}"
    try:
        if side == "+":
            data = (Path(repo) / path).read_bytes()
        else:
            data = subprocess.run(
                ["git", "-C", repo, "show", f"{base_sha}:./{path}"],
                capture_output=True, check=True, timeout=agent_eval.GIT_TIMEOUT_SECONDS,
            ).stdout
        rows = data.decode("utf-8").split("\n")
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
        print(f"warning: {where}: source not readable ({type(exc).__name__}); line_text omitted",
              file=sys.stderr)
        return None
    raw = rows[line - 1] if 0 < line <= len(rows) else None
    if raw is None or row is None or not masks(row, raw):
        print(f"warning: {where}: source line differs from the reviewed unit; line_text omitted",
              file=sys.stderr)
        return None
    return raw


def cmd_log(args: argparse.Namespace) -> int:
    """Record the run in a mechanical out dir and each of its findings."""
    out = Path(args.out).resolve()
    manifest = json.loads((out / "manifest.json").read_text())
    try:
        meta = json.loads((out / "run.json").read_text())
    except FileNotFoundError:
        print(f"no run.json in {out}: run mechanical_review.py first", file=sys.stderr)
        return 1
    units = {f["unit"]: f for f in manifest["files"] if "unit" in f}
    repo = manifest["repo"]
    failed = 0
    # An interrupted review leaves units with no result; that is not a clean file.
    for unit_name in sorted(set(units) - {r.stem for r in (out / "results").glob("*.json")}):
        print(f"FAILED {unit_name}: no result (review not run or interrupted)", file=sys.stderr)
        failed += 1
    results = [json.loads(p.read_text()) for p in sorted((out / "results").glob("*.json"))]
    for result in results:
        if not result.get("ok", True):
            # A failed review is not a clean one; it must not read as 0 findings.
            print(f"FAILED {result['unit']}: {result.get('error')}", file=sys.stderr)
            failed += 1
    input_sha256 = hashlib.sha256(
        "\n".join(sorted(r["input_sha256"] for r in results if "input_sha256" in r)).encode()
    ).hexdigest()
    # Every part comes from the out dir, never from now(), so a rerun gives the same id.
    run_id = agent_eval.short_hash(
        f"{repo}|{meta['base_sha']}|{meta['head_sha']}|{input_sha256}|{meta['started_at']}"
    )
    # run.json fixes the session at review time; an older run.json has no key.
    session_id = meta["session_id"] if "session_id" in meta else os.environ.get("CLAUDE_CODE_SESSION_ID")
    session_id = session_id or None
    records = [record(
        "review_run", run_id,
        agent="blind-review",
        mode=manifest.get("mode", "mechanical"),
        requested_model=meta["requested_model"],
        model_id=",".join(sorted({m for r in results for m in r.get("model_id", "").split(",") if m})),
        effort=meta["effort"],
        cli_version=",".join(sorted({r["cli_version"] for r in results if r.get("cli_version")})),
        repo=repo,
        base=meta["base"],
        base_sha=meta["base_sha"],
        head_sha=meta["head_sha"],
        input_sha256=input_sha256,
        units_total=len(units),
        units_failed=failed,
        **{k: meta[k] for k in USAGE_FIELDS},
        session_id=session_id,
        harness="claude-code" if session_id else None,
        started_at=meta["started_at"],
        finished_at=meta["finished_at"],
    )]
    for result in results:
        if not result.get("ok", True):
            continue
        entry = units[result["unit"]]
        unit = (out / "units" / f"{result['unit']}.diff").read_text()
        unit_hash = hashlib.sha256(unit.encode()).hexdigest()
        unit_rows = {r.partition("|")[0]: r.partition("|")[2] for r in unit.split("\n") if "|" in r}
        for f in result["findings"]:
            # Within one run each unit is reviewed once, so this names one reviewer output.
            fid = agent_eval.short_hash(
                f"{run_id}|{entry['path']}|{unit_hash}|{f['side']}{f['line']}|{f['claim']}"
            )
            base_path = entry.get("base_path", entry["path"])
            line_text = source_line(repo, entry["path"] if f["side"] == "+" else base_path,
                                    f["side"], f["line"], meta["base_sha"],
                                    unit_rows.get(f"{f['side']}{f['line']}"))
            records.append(record(
                "finding", fid,
                run_id=run_id,
                repo=repo,
                path=entry["path"],
                side=f["side"],
                line=f["line"],
                line_text=line_text,
                severity=f["severity"],
                confidence=f["confidence"],
                category=f.get("category", "unknown"),
                claim=f["claim"],
                logged_at=meta["finished_at"],
            ))
    runs, known, _ = load()
    seen = runs.keys() | known.keys()
    new = [r for r in {r["id"]: r for r in records}.values() if r["id"] not in seen]
    for r in new:
        if r["type"] == "finding":
            print(f"{r['id']}  {r['severity']:<6} {r['path']}:{r['side']}{r['line']}  {r['claim'][:70]}")
    if new:
        write(new)
    print(f"logged {sum(r['type'] == 'finding' for r in new)} finding(s) -> {LEDGER}")
    return 1 if failed else 0


def resolve_commit(repo: str, rev: str | None) -> str | None:
    """Resolve an optional user-typed revision to a full SHA, or exit with an error."""
    if rev is None:
        return None
    try:
        return agent_eval.rev_parse(repo, rev)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc


def cmd_mark(args: argparse.Namespace) -> int:
    """Record a human verdict for one finding."""
    findings = load()[1]
    if args.id not in findings:
        print(f"unknown finding {args.id}", file=sys.stderr)
        return 1
    commit = resolve_commit(findings[args.id]["repo"], args.commit)
    write([record("verdict", str(uuid.uuid4()), finding_id=args.id, verdict=args.status,
                  commit=commit, note=args.note or None, auto=False,
                  decided_at=agent_eval.now_ms())])
    return 0


def cmd_reconcile(_: argparse.Namespace) -> int:
    """Mark open added-line findings whose raw line is gone as likely-addressed."""
    records = []
    hashes: dict[Path, set[str] | None] = {}
    for f in load()[1].values():
        if f["status"] != "open" or f["side"] != "+" or f.get("line_text") is None:
            continue
        path = Path(f["repo"]) / f["path"]
        if path not in hashes:
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                source = None  # repo moved or file deleted: not evidence either way
            hashes[path] = None if source is None else {agent_eval.line_hash(r) for r in source.split("\n")}
        if hashes[path] is None:
            continue
        # Raw to raw, as hippo compares: edits above the line move it, so look anywhere.
        if agent_eval.line_hash(f["line_text"]) not in hashes[path]:
            records.append(record("verdict", str(uuid.uuid4()), finding_id=f["id"],
                                  verdict="likely-addressed", note="flagged line changed",
                                  auto=True, decided_at=agent_eval.now_ms()))
    if records:
        write(records)
    print(f"marked {len(records)} finding(s) likely-addressed")
    return 0


def cmd_escape(args: argparse.Namespace) -> int:
    """Record a defect that reached review and that no finding reported."""
    retire_legacy_ledger()
    repo = str(Path(args.repo).resolve())
    fix_commit = resolve_commit(repo, args.commit)
    write([record("escape", str(uuid.uuid4()), repo=repo, path=args.path, line=args.line,
                  fix_commit=fix_commit, note=args.note, recorded_at=agent_eval.now_ms())])
    return 0


def rates(group: list[dict]) -> str:
    """Format usefulness for a group of findings."""
    counts = collections.Counter(f["status"] for f in group)
    judged = sum(counts[s] for s in ("accepted", "false-positive", "not-useful", "likely-addressed"))
    useful = counts["accepted"] + counts["likely-addressed"]
    pct = f"{useful / judged:.0%}" if judged else "n/a"
    fp = f"{counts['false-positive'] / judged:.0%}" if judged else "n/a"
    return f"n={len(group)} useful={pct} false-positive={fp} " + " ".join(
        f"{k}={v}" for k, v in sorted(counts.items())
    )


def cmd_summary(_: argparse.Namespace) -> int:
    """Print usefulness rates overall, by category, by severity, and by model."""
    runs, findings, escapes = load()
    rows = [{**f, "model_id": runs.get(f["run_id"], {}).get("model_id")} for f in findings.values()]
    print(f"overall: {rates(rows)}")
    for field in ("category", "severity", "model_id"):
        groups = collections.defaultdict(list)
        for f in rows:
            groups[f.get(field) or "unknown"].append(f)
        for name, group in sorted(groups.items()):
            print(f"  {field}={name}: {rates(group)}")
    print(f"escaped defects: {len(escapes)}")
    print("useful = accepted + likely-addressed, over findings with a verdict.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested subcommand."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("log")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_log)
    p = sub.add_parser("mark")
    p.add_argument("id")
    p.add_argument("status", choices=STATUSES)
    p.add_argument("--note", default="")
    p.add_argument("--commit", help="commit that addressed the finding; resolved to a full SHA")
    p.set_defaults(func=cmd_mark)
    sub.add_parser("reconcile").set_defaults(func=cmd_reconcile)
    p = sub.add_parser("escape")
    p.add_argument("--repo", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--line", type=int, required=True)
    p.add_argument("--note", required=True)
    p.add_argument("--commit", help="commit that fixed the defect; resolved to a full SHA")
    p.set_defaults(func=cmd_escape)
    sub.add_parser("summary").set_defaults(func=cmd_summary)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
