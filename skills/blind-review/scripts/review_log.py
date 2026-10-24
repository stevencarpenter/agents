#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""review_log.py: track whether real mechanical-review findings were useful.

The benchmark (``bench/bench.py``) scores the reviewer on planted defects.
This ledger measures usefulness on real changes: what happened to each
finding, and which defects reviews missed. It is an append-only JSONL file of
events at ``~/.local/share/blind-review/findings.jsonl``, local because it
holds private repo paths and code lines. The latest status event for a
finding wins.

Subcommands:
  log --out DIR            record every finding of a mechanical run as open
  mark ID STATUS [--note]  STATUS: accepted (the code changed because of it),
                           false-positive, not-useful, duplicate
  reconcile                mark open "+" findings likely-addressed when the
                           flagged line is no longer in the file near its line
  escape --repo R --path P --line N --note TEXT
                           record a defect found later that no review reported
  summary                  usefulness rates overall, by category, and by model
"""

from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

LEDGER = Path(
    os.environ.get("BLIND_REVIEW_LEDGER", Path.home() / ".local/share/blind-review/findings.jsonl")
)
STATUSES = ("accepted", "false-positive", "not-useful", "duplicate")


def now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def append(events: list[dict]) -> None:
    """Append events to the ledger, creating it if needed."""
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def load() -> tuple[dict[str, dict], list[dict]]:
    """Return (findings by ID with their latest status, escape events)."""
    findings: dict[str, dict] = {}
    escapes: list[dict] = []
    if not LEDGER.exists():
        return findings, escapes
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["type"] == "finding":
            findings[event["id"]] = {**event, "status": "open"}
        elif event["type"] == "status" and event["id"] in findings:
            findings[event["id"]]["status"] = event["status"]
        elif event["type"] == "escape":
            escapes.append(event)
    return findings, escapes


def cmd_log(args: argparse.Namespace) -> int:
    """Record each finding in a mechanical out dir as an open finding."""
    out = Path(args.out).resolve()
    manifest = json.loads((out / "manifest.json").read_text())
    paths = {f["unit"]: f["path"] for f in manifest["files"] if "unit" in f}
    run_id = out.name
    events = []
    for result_file in sorted((out / "results").glob("*.json")):
        result = json.loads(result_file.read_text())
        rows = (out / "units" / f"{result['unit']}.diff").read_text().splitlines()
        for f in result["findings"]:
            prefix = f"{f['side']}{f['line']}|"
            line_text = next((r[len(prefix):] for r in rows if r.startswith(prefix)), None)
            key = f"{run_id}|{result['unit']}|{f['side']}{f['line']}|{f['claim']}"
            events.append({
                "type": "finding",
                "id": hashlib.sha256(key.encode()).hexdigest()[:10],
                "logged_at": now(),
                "run_id": run_id,
                "repo": manifest["repo"],
                "base": manifest["base"],
                "path": paths[result["unit"]],
                "side": f["side"],
                "line": f["line"],
                "line_text": line_text,
                "severity": f["severity"],
                "confidence": f["confidence"],
                "category": f.get("category", "unknown"),
                "claim": f["claim"],
                "model_id": result.get("model_id", ""),
            })
    known = load()[0]
    new = [e for e in events if e["id"] not in known]
    append(new)
    for e in new:
        print(f"{e['id']}  {e['severity']:<6} {e['path']}:{e['side']}{e['line']}  {e['claim'][:70]}")
    print(f"logged {len(new)} finding(s) -> {LEDGER}")
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    """Record a human verdict for one finding."""
    findings = load()[0]
    if args.id not in findings:
        print(f"unknown finding {args.id}", file=sys.stderr)
        return 1
    append([{"type": "status", "id": args.id, "status": args.status, "note": args.note,
             "at": now(), "auto": False}])
    return 0


def cmd_reconcile(_: argparse.Namespace) -> int:
    """Mark open added-line findings whose line has since changed as likely-addressed."""
    findings = load()[0]
    events = []
    for f in findings.values():
        if f["status"] != "open" or f["side"] != "+" or f["line_text"] is None:
            continue
        path = Path(f["repo"]) / f["path"]
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue  # repo moved or file deleted: not evidence either way
        window = lines[max(0, f["line"] - 4) : f["line"] + 3]
        if f["line_text"].strip() not in (line.strip() for line in window):
            events.append({"type": "status", "id": f["id"], "status": "likely-addressed",
                           "note": "flagged line changed", "at": now(), "auto": True})
    append(events)
    print(f"marked {len(events)} finding(s) likely-addressed")
    return 0


def cmd_escape(args: argparse.Namespace) -> int:
    """Record a defect that reached review and that no finding reported."""
    append([{"type": "escape", "at": now(), "repo": args.repo, "path": args.path,
             "line": args.line, "note": args.note}])
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
    findings, escapes = load()
    rows = list(findings.values())
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
    p.set_defaults(func=cmd_mark)
    sub.add_parser("reconcile").set_defaults(func=cmd_reconcile)
    p = sub.add_parser("escape")
    p.add_argument("--repo", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--line", type=int, required=True)
    p.add_argument("--note", required=True)
    p.set_defaults(func=cmd_escape)
    sub.add_parser("summary").set_defaults(func=cmd_summary)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
