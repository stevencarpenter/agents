#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""mechanical_review.py: fan mechanical-mode units out to context-free reviewers.

Each unit written by ``strip_context.py mechanical`` goes to its own headless
``claude -p`` process. That process gets this file's fixed brief as its whole
system prompt, the unit text on stdin, no tools, no settings, hooks, plugins,
MCP servers, skills, or CLAUDE.md, and one fixed empty working directory, so
no repository text can reach the model and every unit sees the same harness
text. The exact payload for each unit is written to ``payloads/`` for audit and
the reviewer's answer, with the resolved model ID and an input hash, to
``results/``. ``audit_request.py`` shows the full request the CLI sends.

Usage: mechanical_review.py --out DIR [--model sonnet] [--effort high] [--jobs 4]
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BRIEF = """\
You review one code change. The input holds only the changed lines of one file.
Comments, docstrings, documentation, blank lines, and whitespace-only changes
were removed before you received it. Unchanged code is not shown.

Format: "file <label>" names the file and its language. A row "-N|text" is a
removed line and "+N|text" is an added line; N is the line number on that side
of the change. "@@" separates groups of changed lines that were not adjacent.

Report defects that these lines show: wrong conditions, operators, or
boundaries; unhandled errors; swallowed failures; injection sinks; unsafe
casts or overflow; state or ordering hazards; a removed line whose guard or
effect the added lines no longer provide. Identifier names are not evidence of
behavior. Also report non-idiomatic constructs that a language expert would
change because they make the code less reliable, as category "idiom" with
severity low. Do not report missing comments, missing context, formatting, or
naming.
When a finding depends on code you cannot see, state that assumption and set
confidence to low. Report no findings when you find no defect.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "side": {"enum": ["+", "-"]},
                    "line": {"type": "integer"},
                    "severity": {"enum": ["high", "medium", "low"]},
                    "confidence": {"enum": ["high", "medium", "low"]},
                    "category": {"enum": ["correctness", "security", "reliability", "idiom"]},
                    "claim": {"type": "string"},
                    "evidence": {"type": "string"},
                    "assumption": {"type": "string"},
                },
                "required": [
                    "side",
                    "line",
                    "severity",
                    "confidence",
                    "category",
                    "claim",
                    "evidence",
                ],
            },
        }
    },
    "required": ["findings"],
}


def reviewer_argv(model: str, effort: str) -> list[str]:
    """Build the isolated headless invocation.

    ``--system-prompt`` replaces the default prompt (and with it git status and
    memory paths), ``--safe-mode`` turns off every customization, and
    ``--tools ""`` leaves the model nothing to read with. Not removable without
    ``--bare`` and an API key: a short environment block (temp cwd, platform,
    date) and an account note.
    """
    return [
        "claude",
        "-p",
        "--safe-mode",
        "--setting-sources",
        "",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--tools",
        "",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--system-prompt",
        BRIEF,
        "--json-schema",
        json.dumps(SCHEMA),
        "--output-format",
        "json",
        "--model",
        model,
        "--effort",
        effort,
    ]


# One fixed path: a random temp name would make every request's environment
# block differ (verified with audit_request.py), and the reviewer has no tools,
# so nothing is written here.
SANDBOX = Path(tempfile.gettempdir()) / "blind-review-sandbox"


def sandbox(repo_name: str) -> Path:
    """Return the empty, fixed reviewer working directory, creating it if needed.

    Raises:
        SystemExit: When the directory is a symlink, belongs to another user,
            names the repo, or is not empty.
    """
    SANDBOX.mkdir(exist_ok=True)
    # On a shared /tmp another user could pre-create the path or point it elsewhere.
    if SANDBOX.is_symlink() or (hasattr(os, "getuid") and SANDBOX.stat().st_uid != os.getuid()):
        raise SystemExit(f"sandbox {SANDBOX} is a symlink or not owned by you")
    # The cwd is the one path the reviewer sees; a session scratchpad path names the repo.
    if repo_name in str(SANDBOX):
        raise SystemExit(f"sandbox {SANDBOX} names the repo; set TMPDIR elsewhere")
    if any(SANDBOX.iterdir()):
        raise SystemExit(f"sandbox {SANDBOX} is not empty; remove its contents")
    return SANDBOX


@functools.cache
def cli_version() -> str:
    """Return the ``claude --version`` string; the harness text changes with it."""
    try:
        return subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        return "unavailable"


# A reviewer call that hangs must fail its unit, not stall every other unit.
TIMEOUT_SECONDS = 900


def _findings(reply: object) -> list[dict] | None:
    """Return the reply's findings, or None when they do not match SCHEMA.

    The CLI is asked for SCHEMA, but nothing enforces it here, and a malformed
    finding would crash the ledger and the bench scorer later.
    """
    output = reply.get("structured_output") if isinstance(reply, dict) else None
    findings = output.get("findings") if isinstance(output, dict) else None
    if not isinstance(findings, list):
        return None
    required = SCHEMA["properties"]["findings"]["items"]["required"]
    for f in findings:
        if not isinstance(f, dict) or any(k not in f for k in required):
            return None
        if f["side"] not in ("+", "-") or type(f["line"]) is not int:
            return None
    return findings


def review_unit(unit: Path, out: Path, argv: list[str], repo_name: str) -> dict:
    """Review one unit in a fresh empty directory and record payload and result."""
    text = unit.read_text(encoding="utf-8")
    (out / "payloads" / f"{unit.stem}.json").write_text(
        json.dumps({"argv": argv, "stdin": text}, indent=2), encoding="utf-8"
    )
    reply: object = None
    try:
        proc = subprocess.run(
            argv,
            input=text,
            cwd=sandbox(repo_name),
            capture_output=True,
            text=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired, SystemExit) as exc:
        findings, error = None, f"{type(exc).__name__}: {exc}"
    else:
        try:
            reply = json.loads(proc.stdout)
        except json.JSONDecodeError:
            reply = None
        findings = _findings(reply) if proc.returncode == 0 else None
        if isinstance(reply, dict) and reply.get("is_error"):
            findings = None
        error = str(
            proc.stderr
            or (reply.get("result") if isinstance(reply, dict) else proc.stdout)
            or "no valid structured_output"
        )[-2000:]
    reply_fields = reply if isinstance(reply, dict) else {}
    result = {
        "unit": unit.stem,
        # A reply without valid structured output is a failed review, not a clean file.
        "ok": findings is not None,
        "findings": findings or [],
        "usage": reply_fields.get("usage"),
        "model_id": ",".join(sorted(reply_fields.get("modelUsage") or {})),
        "cli_version": cli_version(),
        "input_sha256": hashlib.sha256(json.dumps([argv, text]).encode()).hexdigest(),
        "error": None if findings is not None else error,
    }
    (out / "results" / f"{unit.stem}.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    """Review every unit in parallel and print a one-line summary per unit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="strip_context.py mechanical --out dir")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--effort", default="high")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    units = sorted((out / "units").glob("*.diff"))
    if not units:
        print(f"no units in {out / 'units'}", file=sys.stderr)
        return 1
    for sub in ("payloads", "results"):
        # Writing through a symlink here could overwrite files outside --out.
        if (out / sub).is_symlink():
            raise SystemExit(f"{out / sub} is a symlink; refusing to write through it")
        (out / sub).mkdir(exist_ok=True)
    repo_name = Path(json.loads((out / "manifest.json").read_text())["repo"]).name
    sandbox(repo_name)  # fail before any review starts
    cmd = reviewer_argv(args.model, args.effort)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda u: review_unit(u, out, cmd, repo_name), units))
    for r in results:
        status = f"{len(r['findings'])} finding(s)" if r["ok"] else f"FAILED: {r['error']}"
        print(f"{r['unit']}: {status}")
    print(f"results in {out / 'results'}")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
