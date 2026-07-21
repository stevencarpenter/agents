#!/usr/bin/env python3
"""generate_context.py — build the curated session-start routing block.

Explicit non-goal: this does NOT dump the agent/skill inventory. Claude Code
already injects the full agent list (with tools) and skill list into the
system prompt every session; repeating that here is negative-value tokens.
This script emits only what that injection does not provide:

  1. Disambiguation rules for overlapping agents that aren't already spelled
     out in the agents' own frontmatter descriptions (routing-overlay.md,
     hand-curated — this is a judgment call, not a fact any config states).
  2. Cross-family shared-rubric overlap the agent names don't reveal
     (e.g. documentation-writer and technical-writer both inline
     technical-writing-guidelines despite dissimilar names).
  3. Declared-vs-installed staleness, on TWO independent pipelines:
       - the canonical agents repo vs what's actually in ~/.claude/agents
       - the personal skills manifest vs what's actually in ~/.claude/skills
     Both are facts injection cannot state, because injection only ever
     reflects the installed set, never a "should be" reference point.
  4. The live MCP server inventory read from ~/.claude.json — a plain
     factual list (not priority judgment; "prefer X over Y" guidance lives
     in the user's global CLAUDE.md already and would be redundant here).
  5. Per-machine capability deltas from the chezmoi machine table, so the
     agent knows what's different about the box it's running on right now.

An earlier version of this script also carried an implementer/reviewer
pairing table and a hand-curated MCP priority quick-map. Both were cut after
a judged bakeoff found they substantially restated facts already visible in
agent names and the user's global CLAUDE.md — see the agents repo's
tools/routing/README.md for that history.

Every non-local source (chezmoi paths) is read best-effort: on a machine
where dotfiles aren't applied, or where a section's source file is absent,
that section is simply omitted rather than erroring. No third-party deps.

Output: a single Markdown block on stdout, sized for direct injection via a
SessionStart hook (see hook-wiring.json, sibling to this file).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path

AGENTS_REPO = Path(__file__).resolve().parents[2]
HOME = Path(os.environ.get("HOME_OVERRIDE", str(Path.home())))
INSTALLED_AGENTS_DIR = Path(os.environ.get("CLAUDE_AGENTS_DIR", str(HOME / ".claude" / "agents")))
INSTALLED_SKILLS_DIR = Path(os.environ.get("CLAUDE_SKILLS_DIR", str(HOME / ".claude" / "skills")))
CLAUDE_JSON = Path(os.environ.get("CLAUDE_JSON", str(HOME / ".claude.json")))
CHEZMOI_SRC = Path(os.environ.get("CHEZMOI_SRC", str(HOME / ".local" / "share" / "chezmoi")))
MACHINES_TOML = CHEZMOI_SRC / ".chezmoidata" / "machines.toml"
SKILLS_MASTER = CHEZMOI_SRC / "dot_config" / "skills" / "skills-master.json"
SKILLS_MACHINE_DIR = CHEZMOI_SRC / "dot_config" / "skills" / "machine"
OVERLAY_MD = Path(__file__).parent / "routing-overlay.md"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Skill families already covered by a routing-overlay disambiguation rule —
# repeating them in the cross-family section would be the inventory-dump
# mistake again, just one level down. Kept as an explicit reviewable list
# rather than fuzzy overlap detection, so a human notices when a NEW family
# needs the same judgment call.
SKIP_SKILL_FAMILIES = {
    "spark-guidelines",
    "spark-pyspark-guidelines",
    "spark-scala-guidelines",
    "data-engineering-guidelines",
}


def parse_frontmatter(text: str) -> dict[str, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        fields[k.strip()] = v.strip()
    return fields


def load_canonical_agents() -> dict[str, dict]:
    agents: dict[str, dict] = {}
    agents_dir = AGENTS_REPO / "agents"
    if not agents_dir.is_dir():
        return agents
    for d in sorted(agents_dir.iterdir()):
        f = d / "agent.md"
        if not f.exists():
            continue
        fm = parse_frontmatter(f.read_text(encoding="utf-8"))
        name = fm.get("name", d.name)
        agents[name] = {
            "skills": [s.strip() for s in fm.get("skills", "").split(",") if s.strip()],
        }
    return agents


def load_installed_agent_names() -> set[str]:
    if not INSTALLED_AGENTS_DIR.is_dir():
        return set()
    return {p.stem for p in INSTALLED_AGENTS_DIR.glob("*.md")}


def load_installed_skill_names() -> set[str]:
    if not INSTALLED_SKILLS_DIR.is_dir():
        return set()
    return {d.name for d in INSTALLED_SKILLS_DIR.iterdir() if (d / "SKILL.md").is_file()}


def deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_declared_personal_skill_names(machine: str) -> set[str] | None:
    """Skills the personal skills-master.json manifest declares for THIS
    machine, after applying its overlay and dropping ``false``-disabled
    entries. Returns None (not "not applicable") when the manifest isn't
    reachable at all, so callers can distinguish "no chezmoi here" from
    "manifest declares zero skills".
    """
    if not SKILLS_MASTER.is_file():
        return None
    try:
        manifest = json.loads(SKILLS_MASTER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    skills = manifest.get("skills", {})
    overlay_path = SKILLS_MACHINE_DIR / f"{machine}.json"
    if overlay_path.is_file():
        try:
            overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            overlay = {}
        skills = deep_merge(skills, overlay.get("skills", {}))
    # .tmpl overlays (personal.json.tmpl etc.) aren't renderable without
    # `chezmoi execute-template`; skip them rather than mis-parsing Go
    # template syntax as plain JSON. This under-counts on machines whose
    # overlay is template-gated, which is a known, stated limitation.
    return {name for name, cfg in skills.items() if cfg is not False}


def load_machines() -> dict:
    if not MACHINES_TOML.is_file():
        return {}
    try:
        return tomllib.loads(MACHINES_TOML.read_text(encoding="utf-8")).get("machines", {})
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def current_machine_key(machines: dict) -> str | None:
    try:
        import subprocess

        out = subprocess.run(
            ["chezmoi", "data", "--format", "json"], capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0:
            data = json.loads(out.stdout)
            key = data.get("machine")
            if key in machines:
                return key
    except Exception:
        pass
    # Best-effort fallback so this still runs on a box without chezmoi.
    return next(iter(machines), None)


def live_mcp_servers() -> dict[str, str]:
    if not CLAUDE_JSON.is_file():
        return {}
    try:
        data = json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    servers = data.get("mcpServers") or {}
    out = {}
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        kind = cfg.get("type", "stdio")
        target = cfg.get("command") or cfg.get("url") or "?"
        out[name] = f"{kind}:{target}"
    return out


def _is_obvious_pair(names: list[str]) -> bool:
    """True when `names` is exactly {X-implementer, X-reviewer} for one X.

    That pairing is already obvious from reading the two agent names side by
    side in the harness's own injected list — restating it here would be
    the inventory-dump mistake the pairing table was cut for.
    """
    if len(names) != 2:
        return False
    suffixes = {"-implementer": None, "-reviewer": None}
    bases = set()
    for name in names:
        matched = False
        for suffix in suffixes:
            if name.endswith(suffix):
                bases.add(name[: -len(suffix)])
                matched = True
                break
        if not matched:
            return False
    return len(bases) == 1


def skill_sharers(agents: dict[str, dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, meta in agents.items():
        for skill in meta["skills"]:
            if skill in SKIP_SKILL_FAMILIES:
                continue
            out.setdefault(skill, []).append(name)
    return {
        k: sorted(v)
        for k, v in out.items()
        if len(v) >= 2 and not _is_obvious_pair(sorted(v))
    }


def render() -> str:
    canonical_agents = load_canonical_agents()
    installed_agent_names = load_installed_agent_names()
    installed_skill_names = load_installed_skill_names()
    machines = load_machines()
    machine = current_machine_key(machines)
    declared_personal_skills = load_declared_personal_skill_names(machine or "")
    mcp_servers = live_mcp_servers()

    lines: list[str] = []
    lines.append("<!-- agent-routing v2 (curated additions only, not an inventory dump) -->")
    lines.append("## Routing notes (adds to, does not repeat, the agent/skill list already in context)")
    lines.append("")

    if OVERLAY_MD.exists():
        lines.append(OVERLAY_MD.read_text(encoding="utf-8").strip())
        lines.append("")

    shared = skill_sharers(canonical_agents)
    if shared:
        lines.append("### Shared rubric overlap the agent names don't reveal")
        for skill, names in sorted(shared.items()):
            lines.append(f"- `{skill}`: {', '.join(names)}")
        lines.append("")

    if canonical_agents:
        canonical_names = set(canonical_agents)
        missing = sorted(canonical_names - installed_agent_names)
        extra = sorted(installed_agent_names - canonical_names)
        lines.append(f"### Agents: {machine or 'this machine'} vs canonical repo")
        if not installed_agent_names:
            lines.append("- no agents installed here (agents capability likely off, or never synced)")
        elif missing:
            lines.append(
                f"- STALE: {len(missing)} agent(s) in the repo aren't installed here yet — "
                f"don't route to them until the next sync: {', '.join(missing)}"
            )
        else:
            lines.append(f"- in sync: all {len(canonical_names)} canonical agents installed")
        if extra:
            lines.append(f"- orphaned locally (removed from repo, still installed): {', '.join(extra)}")
        lines.append("")

    if declared_personal_skills is not None:
        missing_skills = sorted(declared_personal_skills - installed_skill_names)
        if missing_skills:
            lines.append("### Personal skills manifest vs installed")
            lines.append(
                f"- declared but not installed here (last sync may have failed or is pending "
                f"`chezmoi apply`): {', '.join(missing_skills)}"
            )
            lines.append("")

    if mcp_servers:
        lines.append(f"### MCP servers live on this machine right now ({len(mcp_servers)})")
        for name, desc in sorted(mcp_servers.items()):
            lines.append(f"- {name}: {desc}")
        lines.append("")

    if machines:
        off = [m for m, caps in machines.items() if not caps.get("agents", False)]
        if off:
            lines.append("### Per-machine capability deltas")
            lines.append(
                f"- agents capability OFF on: {', '.join(sorted(off))} — none of the "
                f"{len(canonical_agents)} custom agents exist there; expect generic "
                f"Read/Edit/Bash + code-reviewer instead"
            )
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    sys.stdout.write(render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
