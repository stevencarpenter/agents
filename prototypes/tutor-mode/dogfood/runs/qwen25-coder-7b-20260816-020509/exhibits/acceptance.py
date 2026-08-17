#!/usr/bin/env python3
"""Hidden acceptance gate for CALC-102. Never shown to the learner.

Usage: acceptance.py <workspace-dir>  →  JSON verdict on stdout.

Each case runs in its own subprocess with a timeout, so a hostile or broken
implementation (e.g. eval-based code fed an exponentiation tower) cannot hang
or take down the harness. Numeric cases also enforce the ticket's `-> float`
contract; grammar cases enforce that tokens outside `+ - * / ( ) digits .`
raise ExpressionError — including `**` and `//`, which are sequences of
allowed characters that an allowlist-plus-eval shortcut silently accepts
(the exact hole arm 4 shipped).
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys

CASES = [
    {"expr": "2+3*4", "expect": 14.0},
    {"expr": "(1+2.5)*-3", "expect": -10.5},
    {"expr": "10/4", "expect": 2.5},
    {"expr": "2-2-2", "expect": -2.0},
    {"expr": " 2 + 3 * 4 ", "expect": 14.0},
    {"expr": "-(3+4)", "expect": -7.0},
    {"expr": "1/0", "expect": "ExpressionError"},
    {"expr": "", "expect": "ExpressionError"},
    {"expr": "2+", "expect": "ExpressionError"},
    {"expr": "(1+2", "expect": "ExpressionError"},
    {"expr": "2**3", "expect": "ExpressionError"},
    {"expr": "10//4", "expect": "ExpressionError"},
    {"expr": '"42"', "expect": "ExpressionError"},
    {"expr": "1 and 1", "expect": "ExpressionError"},
]

PROBE = r"""
import json, sys
try:
    from calc import evaluate
    v = evaluate(sys.argv[1])
    print(json.dumps({"kind": "value", "type": type(v).__name__, "value": repr(v)}))
except Exception as e:
    print(json.dumps({"kind": "raise", "type": type(e).__name__, "value": str(e)[:200]}))
"""


def run_case(ws: str, expr: str) -> dict:
    try:
        proc = subprocess.run(
            [sys.executable, "-c", PROBE, expr],
            cwd=ws,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return {"kind": "timeout"}
    line = proc.stdout.strip().splitlines()
    if not line:
        return {"kind": "crash", "value": proc.stderr.strip()[-200:]}
    try:
        return json.loads(line[-1])
    except ValueError:
        return {"kind": "crash", "value": line[-1][:200]}


def judge(case: dict, got: dict) -> bool:
    if case["expect"] == "ExpressionError":
        return got.get("kind") == "raise" and got.get("type") == "ExpressionError"
    if got.get("kind") != "value" or got.get("type") != "float":
        return False
    try:
        # got["value"] is repr() of the learner function's return value and is
        # attacker-influenced; literal_eval only accepts Python literals, so a
        # non-numeric repr fails the case instead of executing anything.
        return abs(float(ast.literal_eval(got["value"])) - case["expect"]) < 1e-9
    except Exception:
        return False


def main() -> int:
    ws = sys.argv[1]
    results = []
    for case in CASES:
        got = run_case(ws, case["expr"])
        results.append(
            {
                "expr": case["expr"],
                "expect": case["expect"] if case["expect"] == "ExpressionError" else f"float {case['expect']}",
                "got": got,
                "pass": judge(case, got),
            }
        )
    passed = sum(1 for r in results if r["pass"])
    print(
        json.dumps(
            {
                "task": "calc-102",
                "passed": passed,
                "total": len(results),
                "all_pass": passed == len(results),
                "cases": results,
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
