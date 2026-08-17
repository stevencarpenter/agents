#!/usr/bin/env python3
"""Layer-1 facts for a tutor-bench run — deterministic, recomputable.

Usage: mechanical.py <run-dir>  →  facts JSON on stdout.

v2 dirs (manifest.json with schema_version 2) are fully self-describing.
v1 legacy dirs are reconstructed from transcript referee lines plus
`legacy-facts-v1.json` (gate results with documented provenance).
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
CODEISH = re.compile(r"^\s*(def |class |return |assert |import )", re.M)
FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)


def tutor_sections(transcript: str) -> list[str]:
    # Sections start at "## Turn N — tutor" and run to the next "## " header.
    return re.findall(r"^## Turn \d+ — tutor\n(.*?)(?=^## |^---$|\Z)", transcript, re.M | re.S)


def chat_code_flags(transcript: str) -> list[str]:
    flags = []
    for section in tutor_sections(transcript):
        for m in FENCE.finditer(section):
            body = m.group(1)
            if CODEISH.search(body):
                flags.append(body.strip().splitlines()[0][:120])
    return flags


def v1_facts(run: pathlib.Path, transcript: str) -> dict:
    learner_turns = len(re.findall(r"^## Turn \d+ — learner", transcript, re.M))
    done = "_Learner declared DONE with green tests — stopping._" in transcript
    mutations = len(re.findall(r"VIOLATION: tutor turn mutated", transcript))
    legacy = json.loads((HERE / "legacy-facts-v1.json").read_text(encoding="utf-8"))
    entry = legacy.get(run.name, {})
    return {
        "schema": 1,
        "completed": done,
        "turns_to_done": learner_turns,
        "gate_passed": entry.get("gate_passed"),
        "gate_total": entry.get("gate_total"),
        "gate_provenance": entry.get("provenance"),
        "tutor_mutations": mutations,
        "continuity": entry.get("continuity", True),
        "ablation": entry.get("ablation", False),
    }


def v2_facts(run: pathlib.Path) -> dict:
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    accept = json.loads((run / "acceptance.json").read_text(encoding="utf-8"))
    metrics = manifest.get("metrics", {})
    return {
        "schema": 2,
        "completed": manifest["outcome"]["learner_done"],
        "turns_to_done": metrics.get("turns_learner"),
        "gate_passed": accept.get("passed"),
        "gate_total": accept.get("total"),
        "tutor_mutations": manifest["outcome"]["tutor_mutations"],
        "continuity": manifest["tutor_session"]["continuous"],
        "tool_uses": manifest["tutor_session"].get("tool_uses"),
        "tutor_cost_usd": round(metrics.get("tutor_cost_usd", 0), 4),
        "wall_s": metrics.get("wall_s"),
        "learner_tokens_out": metrics.get("learner_tokens_out"),
        "ablation": False,
    }


def main() -> int:
    run = pathlib.Path(sys.argv[1]).resolve()
    transcript = (run / "transcript.md").read_text(encoding="utf-8")
    if (run / "manifest.json").exists() and json.loads(
        (run / "manifest.json").read_text(encoding="utf-8")
    ).get("schema_version") == 2:
        facts = v2_facts(run)
    else:
        facts = v1_facts(run, transcript)
    facts["learner_turns"] = len(re.findall(r"^## Turn \d+ — learner", transcript, re.M))
    flags = chat_code_flags(transcript)
    facts["chat_code_flags"] = len(flags)
    facts["chat_code_flag_excerpts"] = flags[:10]
    print(json.dumps(facts, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
