#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""audit_request.py: show the exact request a mechanical reviewer receives.

Points ``ANTHROPIC_BASE_URL`` at a local server that records the request body
and answers with an error, so no model call is made. It sends one unit twice
with the same argv ``mechanical_review.py`` uses, then prints the system text,
the messages, and every line that differs between the two requests. It fails
when the repo name or path appears anywhere in a request. Rerun it after a
Claude Code upgrade: the harness text belongs to the CLI, not to this repo.

Usage: audit_request.py --out DIR   (a ``strip_context.py mechanical`` out dir)
"""

from __future__ import annotations

import argparse
import difflib
import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mechanical_review


def capture(argv: list[str], text: str, cwd: Path) -> list[dict]:
    """Run the reviewer once against a recording server and return every request body.

    One invocation sends several requests (retries after the stub's 400), and
    a leak in any of them reaches the model.
    """
    bodies: list[bytes] = []

    class Recorder(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            bodies.append(self.rfile.read(int(self.headers.get("content-length", 0))))
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"type":"error","error":{"type":"invalid_request_error"}}')

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {**os.environ, "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}"}
    try:
        subprocess.run(
            argv, input=text, cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
            check=False,
        )
    finally:
        server.shutdown()
    if not bodies:
        raise SystemExit("the CLI sent no request; ANTHROPIC_BASE_URL may be ignored")
    parsed = [json.loads(raw) for raw in bodies]
    for body in parsed:
        body.pop("metadata", None)  # per-session IDs, not prompt content
    return parsed


def texts(body: dict) -> list[tuple[str, str]]:
    """Flatten a request body into (where, text) pairs for printing."""
    system = body.get("system", [])
    rows = [("system", b["text"]) for b in (system if isinstance(system, list) else [])]
    rows += [("system", system)] if isinstance(system, str) else []
    for message in body.get("messages", []):
        content = message["content"]
        for block in content if isinstance(content, list) else [{"text": content}]:
            rows.append((message["role"], block.get("text", json.dumps(block))))
    return rows


def main(argv: list[str] | None = None) -> int:
    """Capture two requests for the first unit and report leaks and variance."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--effort", default="high")
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    repo = Path(json.loads((out / "manifest.json").read_text())["repo"])
    unit = min((out / "units").glob("*.diff"))
    cmd = mechanical_review.reviewer_argv(args.model, args.effort)
    cwd = mechanical_review.sandbox(repo.name)
    run_a, run_b = (capture(cmd, unit.read_text(), cwd) for _ in range(2))
    first, second = run_a[0], run_b[0]

    print(f"model={first.get('model')} temperature={first.get('temperature')} "
          f"thinking={first.get('thinking')} tools={[t.get('name') for t in first.get('tools', [])]}")
    for where, text in texts(first):
        print(f"--- {where} ---\n{text}")
    raw = json.dumps(run_a + run_b)
    leaks = [needle for needle in (str(repo), repo.name) if needle in raw]
    a = json.dumps(first, indent=1, sort_keys=True).splitlines()
    b = json.dumps(second, indent=1, sort_keys=True).splitlines()
    changed = [line for line in difflib.unified_diff(a, b, lineterm="", n=0)
               if line[:1] in "+-" and not line.startswith(("+++", "---"))]
    print("=== differences between the two requests ===")
    print("\n".join(changed) or "none")
    if leaks:
        print(f"LEAK: request contains {leaks}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
