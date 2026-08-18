#!/usr/bin/env python3
"""Hands for the local-model learner.

Reads the learner's raw chat text on stdin. Every fenced block whose info
string is `file:<relative-path>` is written verbatim into the workspace (whole-
file replace — the learner has no partial editor). Prints the remaining text
(the chat message for the tutor) to stdout and a `saved: ...` manifest line to
stderr. Thinking tags are stripped. Paths may not be absolute or contain `..`.
"""

from __future__ import annotations

import pathlib
import re
import sys

# Accept `file:name` anywhere in the fence info string ("```file:calc.py" and
# the common small-model slip "```python file:calc.py").
FENCE = re.compile(r"```[^\n`]*?file:([^\n`]+)\n(.*?)```", re.S)
THINK = re.compile(r"<think>.*?</think>", re.S)


def apply(text: str, ws: pathlib.Path) -> tuple[str, list[str]]:
    text = THINK.sub("", text)
    chat_parts: list[str] = []
    saved: list[str] = []
    last = 0
    for m in FENCE.finditer(text):
        chat_parts.append(text[last : m.start()])
        last = m.end()
        name = m.group(1).strip()
        if name.startswith("/") or ".." in pathlib.PurePosixPath(name).parts:
            chat_parts.append(f"[rejected unsafe path: {name}]")
            continue
        path = ws / name
        path.parent.mkdir(parents=True, exist_ok=True)
        body = m.group(2)
        if not body.endswith("\n"):
            body += "\n"
        path.write_text(body, encoding="utf-8")
        saved.append(name)
    chat_parts.append(text[last:])
    chat = re.sub(r"\n{3,}", "\n\n", "".join(chat_parts)).strip()
    return chat, saved


def main() -> int:
    ws = pathlib.Path(sys.argv[1])
    chat, saved = apply(sys.stdin.read(), ws)
    print(chat)
    if saved:
        print("saved: " + ", ".join(saved), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
