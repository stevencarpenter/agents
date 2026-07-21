#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap candidate agents from hippo.db")
    parser.add_argument("--db", default=str(Path.home() / ".local/share/hippo/hippo.db"))
    parser.add_argument("--out", default="mining/candidates")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """
            SELECT project_dir, COUNT(*) AS sessions
            FROM claude_sessions
            WHERE is_subagent = 1
            GROUP BY project_dir
            ORDER BY sessions DESC 
            LIMIT 10
            """
        ).fetchall()
    finally:
        connection.close()

    for project_dir, sessions in rows:
        name = _slug(project_dir)
        if not name:
            continue
        (out / f"{name}.md").write_text(
            _candidate_markdown(name, project_dir, sessions),
            encoding="utf-8",
        )

    print(f"wrote {len(rows)} candidate sketches to {out}")
    return 0


def _slug(value: str) -> str:
    cleaned = value.strip("-/").replace("-Users-carpenter-projects-", "")
    chars = [char.lower() if char.isalnum() else "-" for char in cleaned]
    return "-".join(part for part in "".join(chars).split("-") if part)[:80]


def _candidate_markdown(name: str, project_dir: str, sessions: int) -> str:
    return f"""---
name: {name}
description: Use when working on recurring tasks from {project_dir}.
x-derived-from: hippo-subagent-count-{sessions}
---

Draft candidate from {sessions} delegated hippo sessions for `{project_dir}`.

Human review required before promotion.
"""


if __name__ == "__main__":
    raise SystemExit(main())
