#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""log_pair.py: append one blind-vs-context paired-review record as JSONL.

Reads a JSON object from a file argument (or stdin), stamps recorded_at,
and appends it as one line to ~/.local/share/blind-review/pairs.jsonl.
Part of the blind-review PoC; the pair log is the eval dataset for whether
context-blind review surfaces different findings than status-quo review.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

LOG = Path.home() / ".local" / "share" / "blind-review" / "pairs.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", nargs="?", type=Path, help="JSON record file (default: stdin)")
    args = parser.parse_args(argv)
    raw = args.record.read_text(encoding="utf-8") if args.record else sys.stdin.read()
    record = json.loads(raw)
    if not isinstance(record, dict):
        raise SystemExit("the record must be a JSON object")
    record.setdefault(
        "recorded_at",
        datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    )
    record.setdefault("poc", True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"logged pair record -> {LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
