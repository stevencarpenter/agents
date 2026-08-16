#!/usr/bin/env python3
"""Normalize a Claude Code session JSONL into a per-tool-use event stream.

Usage: extract_tool_uses.py <session.jsonl>  →  tool-uses JSONL on stdout.

One output line per tool_use block: {seq, driver_turn, tool, input,
result_excerpt, is_error}. driver_turn counts top-level plain-text user
messages seen so far — in this harness each driver turn injects exactly one
user text message into the tutor session, so the count attributes tool calls
to the learner message that provoked them. Best-effort by design: entries this
script cannot parse are skipped and the verbatim JSONL remains the source of
truth. Result excerpts are truncated; full outputs live in the JSONL.
"""

from __future__ import annotations

import json
import sys

EXCERPT = 500


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def main() -> int:
    path = sys.argv[1]
    uses: dict[str, dict] = {}
    order: list[str] = []
    driver_turn = 0
    seq = 0

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            msg = entry.get("message")
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if entry.get("type") == "user" and isinstance(content, str):
                driver_turn += 1
                continue
            if not isinstance(content, list):
                continue
            saw_tool_result = False
            plain_user_text = False
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    seq += 1
                    uid = block.get("id", f"noid-{seq}")
                    uses[uid] = {
                        "seq": seq,
                        "driver_turn": driver_turn,
                        "tool": block.get("name"),
                        "input": block.get("input"),
                        "result_excerpt": None,
                        "is_error": None,
                    }
                    order.append(uid)
                elif btype == "tool_result":
                    saw_tool_result = True
                    uid = block.get("tool_use_id")
                    if uid in uses:
                        raw = text_of(block.get("content"))
                        uses[uid]["result_excerpt"] = raw[:EXCERPT]
                        uses[uid]["is_error"] = bool(block.get("is_error"))
                elif btype == "text" and entry.get("type") == "user":
                    plain_user_text = True
            if plain_user_text and not saw_tool_result:
                driver_turn += 1

    for uid in order:
        print(json.dumps(uses[uid]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
