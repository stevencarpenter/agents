from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_registry.agents import (
    Agent,
    compose_agent_with_skills,
    validate_agent_tree,
    validate_skill_closure,
    validate_skill_tree,
)
from agent_registry.claude_code import emit_claude_agent
from agent_registry.codex import CODEX_EXT, emit_codex_agent
from agent_registry.copilot import emit_copilot_instructions
from agent_registry.cursor import CURSOR_EXT, emit_cursor_agent
from agent_registry.opencode import emit_opencode_agent

_MANIFEST = ".installed-by-agent-registry.json"


def _load_agents(agents_dir: str, skills_dir: str) -> list[Agent]:
    """Load + validate agents, inlining any shared skills they opt into.

    Agents that declare a ``skills:`` frontmatter field get those skills' bodies
    inlined into their prompt (see ``compose_agent_with_skills``), so every
    emit/install target ships a self-contained agent. Raises if an agent
    references a skill that does not exist.

    Args:
        agents_dir: Path to the agent tree (``agents/`` by default).
        skills_dir: Path to the skill tree (``skills/`` by default).

    Returns:
        The validated agents with shared skills inlined.
    """
    agents = validate_agent_tree(Path(agents_dir))
    skills_by_name = {s.name: s for s in validate_skill_tree(Path(skills_dir))}
    return [compose_agent_with_skills(a, skills_by_name) for a in agents]


def main() -> int:
    parser = argparse.ArgumentParser(prog="agent-registry")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--agents-dir", default="agents")
    validate_parser.add_argument("--skills-dir", default="skills")

    emit_claude_parser = subparsers.add_parser("emit-claude")
    emit_claude_parser.add_argument("--agents-dir", default="agents")
    emit_claude_parser.add_argument("--skills-dir", default="skills")
    emit_claude_parser.add_argument("--out-dir", default="build/claude/agents")

    emit_codex_parser = subparsers.add_parser("emit-codex")
    emit_codex_parser.add_argument("--agents-dir", default="agents")
    emit_codex_parser.add_argument("--skills-dir", default="skills")
    emit_codex_parser.add_argument("--out-dir", default="build/codex/agents")

    emit_opencode_parser = subparsers.add_parser("emit-opencode")
    emit_opencode_parser.add_argument("--agents-dir", default="agents")
    emit_opencode_parser.add_argument("--skills-dir", default="skills")
    emit_opencode_parser.add_argument("--out-dir", default="build/opencode/agents")

    emit_copilot_parser = subparsers.add_parser("emit-copilot")
    emit_copilot_parser.add_argument("--agents-dir", default="agents")
    emit_copilot_parser.add_argument("--skills-dir", default="skills")
    emit_copilot_parser.add_argument("--out-dir", default="build/copilot")

    emit_cursor_parser = subparsers.add_parser("emit-cursor")
    emit_cursor_parser.add_argument("--agents-dir", default="agents")
    emit_cursor_parser.add_argument("--skills-dir", default="skills")
    emit_cursor_parser.add_argument("--out-dir", default="build/cursor/agents")

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--agents-dir", default="agents")
    install_parser.add_argument("--skills-dir", default="skills")
    install_parser.add_argument(
        "--target",
        choices=["claude", "codex", "opencode", "copilot", "cursor", "all"],
        default="all",
    )

    args = parser.parse_args()

    if args.command == "validate":
        agents = validate_agent_tree(Path(args.agents_dir))
        skills = validate_skill_tree(Path(args.skills_dir))
        skills_by_name = {s.name: s for s in skills}
        # Fail loudly on dangling `skills:` references so CI/`just check` catch them.
        for agent in agents:
            compose_agent_with_skills(agent, skills_by_name)
        # And on skill-body "apply `X`" instructions not satisfied by every
        # consuming agent's skills: field (inlining closure).
        validate_skill_closure(agents, skills)
        print(f"validated {len(agents)} agents and {len(skills)} skills")
        return 0

    if args.command == "emit-claude":
        agents = _load_agents(args.agents_dir, args.skills_dir)
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for agent in agents:
            (out_dir / f"{agent.name}.md").write_text(emit_claude_agent(agent), encoding="utf-8")
        print(f"emitted {len(agents)} claude agents to {out_dir}")
        return 0

    if args.command == "emit-codex":
        agents = _load_agents(args.agents_dir, args.skills_dir)
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for agent in agents:
            (out_dir / f"{agent.name}{CODEX_EXT}").write_text(emit_codex_agent(agent), encoding="utf-8")
        print(f"emitted {len(agents)} codex agents to {out_dir}")
        return 0

    if args.command == "emit-opencode":
        agents = _load_agents(args.agents_dir, args.skills_dir)
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for agent in agents:
            (out_dir / f"{agent.name}.md").write_text(emit_opencode_agent(agent), encoding="utf-8")
        print(f"emitted {len(agents)} opencode agents to {out_dir}")
        return 0

    if args.command == "emit-copilot":
        agents = _load_agents(args.agents_dir, args.skills_dir)
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        content = emit_copilot_instructions(agents)
        (out_dir / "global-agents-instructions.md").write_text(content, encoding="utf-8")
        print(f"emitted copilot instructions ({len(agents)} agents) to {out_dir}")
        return 0

    if args.command == "emit-cursor":
        agents = _load_agents(args.agents_dir, args.skills_dir)
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for agent in agents:
            (out_dir / f"{agent.name}{CURSOR_EXT}").write_text(emit_cursor_agent(agent), encoding="utf-8")
        print(f"emitted {len(agents)} cursor agents to {out_dir}")
        return 0

    if args.command == "install":
        all_agents = _load_agents(args.agents_dir, args.skills_dir)
        home = Path.home()
        targets = (
            ["claude", "codex", "opencode", "copilot", "cursor"] if args.target == "all" else [args.target]
        )

        if "claude" in targets:
            files = {f"{a.name}.md": emit_claude_agent(a) for a in all_agents}
            n = _sync_dir(home / ".claude" / "agents", files)
            print(f"installed {n} agents → ~/.claude/agents")

        if "codex" in targets:
            files = {f"{a.name}{CODEX_EXT}": emit_codex_agent(a) for a in all_agents}
            n = _sync_dir(home / ".codex" / "agents", files)
            print(f"installed {n} agents → ~/.codex/agents (TOML)")

        if "opencode" in targets:
            files = {f"{a.name}.md": emit_opencode_agent(a) for a in all_agents}
            n = _sync_dir(home / ".config" / "opencode" / "agents", files)
            print(f"installed {n} agents → ~/.config/opencode/agents")

        if "copilot" in targets:
            dest = home / ".config" / "github-copilot"
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "global-agents-instructions.md").write_text(
                emit_copilot_instructions(all_agents), encoding="utf-8"
            )
            print(f"installed {len(all_agents)} agents → ~/.config/github-copilot/global-agents-instructions.md")
            # The github-copilot dir is only partially chezmoi-managed; warn only
            # if chezmoi actually tracks THIS file (any prefix/.tmpl variant).
            cm_src = home / ".local" / "share" / "chezmoi" / "dot_config" / "github-copilot"
            if cm_src.exists() and any(cm_src.glob("*global-agents-instructions.md*")):
                print("  note: chezmoi also tracks this file — manage it there so `chezmoi apply` doesn't overwrite it")

        if "cursor" in targets:
            files = {f"{a.name}{CURSOR_EXT}": emit_cursor_agent(a) for a in all_agents}
            n = _sync_dir(home / ".cursor" / "agents", files)
            print(f"installed {n} agents → ~/.cursor/agents")

        return 0

    raise AssertionError(f"unhandled command: {args.command}")


def _sync_dir(dest: Path, files: dict[str, str]) -> int:
    """Write files into dest and prune only previously-installed files.

    A manifest in dest tracks which filenames this tool owns, so hand-written
    files the user placed in the same directory are never touched.
    """
    dest.mkdir(parents=True, exist_ok=True)
    manifest_path = dest / _MANIFEST

    previously_owned: set[str] = set()
    if manifest_path.exists():
        try:
            previously_owned = set(json.loads(manifest_path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            previously_owned = set()

    for name, content in files.items():
        (dest / name).write_text(content, encoding="utf-8")

    for stale in previously_owned - set(files):
        target = dest / stale
        if target.exists():
            target.unlink()

    manifest_path.write_text(json.dumps(sorted(files), indent=2), encoding="utf-8")
    return len(files)


if __name__ == "__main__":
    raise SystemExit(main())
