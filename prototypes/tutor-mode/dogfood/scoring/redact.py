#!/usr/bin/env python3
"""Blind a transcript for judging: replace model identities with placeholders.

Usage: redact.py <run-dir>  →  redacted transcript on stdout.

Learner model ids are taken from the transcript's own headers (and manifest
when present) so the judge cannot grade on model reputation. Tutor model
mentions in headers are masked likewise. Referee lines are left untouched.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys


def main() -> int:
    run = pathlib.Path(sys.argv[1]).resolve()
    text = (run / "transcript.md").read_text(encoding="utf-8")

    models: set[str] = set()
    for m in re.finditer(r"— learner \(([^)]+)\)", text):
        models.add(m.group(1))
    manifest = run / "manifest.json"
    if manifest.exists():
        try:
            cfg = json.loads(manifest.read_text(encoding="utf-8")).get("config", {})
            if cfg.get("learner", {}).get("model"):
                models.add(cfg["learner"]["model"])
        except ValueError:
            pass

    for model in sorted(models, key=len, reverse=True):
        text = text.replace(model, "LEARNER-MODEL")
    text = re.sub(r"(?m)^(- learner: ).*$", r"\1LEARNER-MODEL (chat-only, driver hands)", text)
    text = re.sub(r"(?m)^(- tutor: ).*$", r"\1TUTOR-MODEL + outputStyle=Tutor", text)
    text = re.sub(r"(?m)^(- model: ).*$", r"\1REDACTED", text)
    # Run ids and workspace paths encode the learner model in their prefix.
    text = re.sub(r"(?m)^(# Tutor-bench transcript — ).*$", r"\1[RUN-REDACTED]", text)
    text = re.sub(r"(?m)^(# Tutor-mode dogfood transcript.*)$", "# Tutor session transcript [RUN-REDACTED]", text)
    text = re.sub(r"(?m)^(- max turns: \d+) · workspace: .*$", r"\1 · workspace: [PATH-REDACTED]", text)

    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
