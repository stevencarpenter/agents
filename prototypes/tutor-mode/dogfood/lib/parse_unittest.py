#!/usr/bin/env python3
"""Parse `python -m unittest` output (stdin) into a one-line JSON verdict:
{ran, failures, errors, ok}. `ran` is -1 when no "Ran N tests" line exists
(e.g. import crash before the runner started)."""

from __future__ import annotations

import json
import re
import sys


def main() -> int:
    text = sys.stdin.read()
    ran = -1
    m = re.search(r"^Ran (\d+) tests?", text, re.M)
    if m:
        ran = int(m.group(1))
    failures = errors = 0
    m = re.search(r"FAILED \(([^)]*)\)", text)
    if m:
        for part in m.group(1).split(","):
            part = part.strip()
            if part.startswith("failures="):
                failures = int(part.split("=")[1])
            elif part.startswith("errors="):
                errors = int(part.split("=")[1])
    ok = bool(re.search(r"^OK\b", text, re.M)) and ran > 0
    print(json.dumps({"ran": ran, "failures": failures, "errors": errors, "ok": ok}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
