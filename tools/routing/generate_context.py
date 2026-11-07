#!/usr/bin/env python3
"""Build the curated session-start routing block.
Emit Markdown on stdout; see tools/routing/README.md for behavior and deployment.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

AGENTS_REPO = Path(__file__).resolve().parents[2]
HOME = Path(os.environ.get("HOME_OVERRIDE", str(Path.home())))
INSTALLED_AGENTS_DIR = Path(os.environ.get("CLAUDE_AGENTS_DIR", str(HOME / ".claude" / "agents")))
INSTALLED_SKILLS_DIR = Path(os.environ.get("CLAUDE_SKILLS_DIR", str(HOME / ".claude" / "skills")))
CLAUDE_JSON = Path(os.environ.get("CLAUDE_JSON", str(HOME / ".claude.json")))
# dfm links the skills manifest and this host's identity overlay here from ~/.dotfiles.
SKILLS_CONFIG_DIR = Path(os.environ.get("SKILLS_CONFIG_DIR", str(HOME / ".config" / "skills")))
SKILLS_MASTER = SKILLS_CONFIG_DIR / "skills-master.json"
SKILLS_MACHINE_DIR = SKILLS_CONFIG_DIR / "machine"
OVERLAY_MD = Path(__file__).parent / "routing-overlay.md"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Families the overlay already disambiguates. An explicit list, so a new family forces a review.
SKIP_SKILL_FAMILIES = {
    "spark-guidelines",
    "spark-pyspark-guidelines",
    "spark-scala-guidelines",
    "data-engineering-guidelines",
    # unreal-* agents also inline cpp-guidelines; overlay rule 8 covers that split.
    "cpp-guidelines",
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


def load_declared_personal_skill_names(machine: str) -> set[str] | None:
    """Skills the manifest declares for this machine after its overlay.

    None when the manifest is unreachable, which is not the same as zero skills.
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
        skills = skills | overlay.get("skills", {})
    return {name for name, cfg in skills.items() if cfg is not False}


def current_identity() -> str | None:
    """The dfm identity (personal, work, lab) of this host.

    ``DFM_IDENTITY`` is the same seam the dotfiles sync scripts honour. Without
    it, the identity module links exactly one overlay into the machine dir, so
    its stem is the identity. Anything else (no overlay, several) is unknown.
    """
    env = os.environ.get("DFM_IDENTITY")
    if env:
        return env
    if not SKILLS_MACHINE_DIR.is_dir():
        return None
    overlays = [p.stem for p in SKILLS_MACHINE_DIR.glob("*.json")]
    return overlays[0] if len(overlays) == 1 else None


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
    """Implementer/reviewer pairs are obvious from the harness's own agent list; skip them."""
    return (
        len(names) == 2
        and all(name.endswith(("-implementer", "-reviewer")) for name in names)
        and len({name.rsplit("-", 1)[0] for name in names}) == 1
    )


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
    machine = current_identity()
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
                f"- STALE: {len(missing)} agent(s) in the repo aren't installed here yet. "
                f"Don't route to them until the next sync: {', '.join(missing)}"
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
                f"- declared but not installed here (last skills sync may have failed or is "
                f"pending `scripts/hooks-sync.sh` in dotfiles): {', '.join(missing_skills)}"
            )
            lines.append("")

    if mcp_servers:
        lines.append(f"### MCP servers live on this machine right now ({len(mcp_servers)})")
        for name, desc in sorted(mcp_servers.items()):
            lines.append(f"- {name}: {desc}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    sys.stdout.write(render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
