from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import tomllib

from agent_registry.agents import (
    Agent,
    agent_skill_refs,
    compose_agent_with_skills,
    validate_agent_tree,
    validate_isolated_read_only,
    validate_skill_closure,
    validate_skill_tree,
)
from agent_registry.claude_code import emit_claude_agent
from agent_registry.codex import CODEX_EXT, emit_codex_agent
from agent_registry.copilot import emit_copilot_instructions
from agent_registry.cursor import CURSOR_EXT, emit_cursor_agent
from agent_registry.opencode import emit_opencode_agent

_MANIFEST = ".installed-by-agent-registry.json"
_SYNC_MANIFEST = "sync-manifest.toml"


@dataclass(frozen=True)
class SyncSelection:
    """Names excluded from installation by the sync manifest."""

    disabled_agents: frozenset[str] = frozenset()
    disabled_skills: frozenset[str] = frozenset()
    # Every name the manifest lists, enabled or not, so typos are caught either way.
    listed_agents: frozenset[str] = field(default=frozenset(), compare=False)
    listed_skills: frozenset[str] = field(default=frozenset(), compare=False)


def load_sync_selection(path: Path) -> SyncSelection:
    """Read the opt-out lists. A missing manifest selects everything."""
    if not path.is_file():
        return SyncSelection()
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    if data.get("schema", 1) != 1:
        raise ValueError(f"unsupported sync manifest schema: {data.get('schema')}")

    def names(section: str) -> tuple[frozenset[str], frozenset[str]]:
        entry = data.get(section, {})
        if not isinstance(entry, dict):
            raise ValueError(f"[{section}] must be a table")
        for name, enabled in entry.items():
            if not isinstance(enabled, bool):
                raise ValueError(f"[{section}].{name} must be true or false")
        disabled = frozenset(name for name, enabled in entry.items() if not enabled)
        return disabled, frozenset(entry)

    agents_off, agents_listed = names("agents")
    skills_off, skills_listed = names("skills")
    return SyncSelection(agents_off, skills_off, agents_listed, skills_listed)


def _without_skills(agent: Agent, disabled: frozenset[str]) -> Agent:
    """Drop disabled rubric names so their bodies are not inlined."""
    refs = [name for name in agent_skill_refs(agent) if name not in disabled]
    metadata = dict(agent.metadata)
    metadata["skills"] = ", ".join(refs)
    return Agent(agent.path, agent.name, metadata, agent.body)


def _load_agents(
    agents_dir: str,
    skills_dir: str,
    selection: SyncSelection | None = None,
    *,
    apply: bool = True,
) -> list[Agent]:
    """Load and validate agents with their skills inlined.

    Raises on an unknown skill or a skill-closure violation, so no command can
    emit or install an agent that `validate` rejects. With `apply`, names in the
    sync manifest are excluded from the returned list and from inlined rubrics.
    """
    agents = validate_agent_tree(Path(agents_dir))
    skills = validate_skill_tree(Path(skills_dir))
    validate_skill_closure(agents, skills)
    selection = selection or SyncSelection()
    unknown = (
        (selection.disabled_agents | selection.listed_agents) - {a.name for a in agents}
    ) | ((selection.disabled_skills | selection.listed_skills) - {s.name for s in skills})
    if unknown:
        raise ValueError(f"sync manifest lists unknown names: {sorted(unknown)}")
    if apply:
        if selection.disabled_agents:
            agents = [a for a in agents if a.name not in selection.disabled_agents]
        if selection.disabled_skills:
            agents = [_without_skills(a, selection.disabled_skills) for a in agents]
    skills_by_name = {s.name: s for s in skills}
    return [compose_agent_with_skills(a, skills_by_name) for a in agents]


def main() -> int:
    parser = argparse.ArgumentParser(prog="agent-registry")
    subparsers = parser.add_subparsers(dest="command", required=True)
    source_parser = argparse.ArgumentParser(add_help=False)
    source_parser.add_argument("--agents-dir", default="agents")
    source_parser.add_argument("--skills-dir", default="skills")
    source_parser.add_argument("--sync-manifest", default=None)
    emit_targets = ("claude", "codex", "opencode", "copilot", "cursor")

    subparsers.add_parser("validate", parents=[source_parser])
    for target in emit_targets:
        emit_parser = subparsers.add_parser(f"emit-{target}", parents=[source_parser])
        out_dir = f"build/{target}" if target == "copilot" else f"build/{target}/agents"
        emit_parser.add_argument("--out-dir", default=out_dir)

    install_parser = subparsers.add_parser("install", parents=[source_parser])
    install_parser.add_argument(
        "--target",
        choices=[*emit_targets, "all"],
        default="all",
    )

    args = parser.parse_args()
    # A custom agents dir implies its own checkout root; do not apply this
    # repo's manifest to fixtures or another tree.
    manifest = args.sync_manifest or str(Path(args.agents_dir).parent / _SYNC_MANIFEST)
    selection = load_sync_selection(Path(manifest))

    # Validate every target before any write, so `install --target all` cannot half-install.
    if args.command != "validate":
        agents = _load_agents(args.agents_dir, args.skills_dir, selection)
        targets = (
            list(emit_targets)
            if args.command == "install" and args.target == "all"
            else [args.target if args.command == "install" else args.command.removeprefix("emit-")]
        )
        for agent in agents:
            for target in targets:
                validate_isolated_read_only(agent, target)

    if args.command == "validate":
        agents = _load_agents(args.agents_dir, args.skills_dir, selection, apply=False)
        skills = validate_skill_tree(Path(args.skills_dir))
        print(f"validated {len(agents)} agents and {len(skills)} skills")
        return 0

    emitters = {
        "claude": (emit_claude_agent, ".md"),
        "codex": (emit_codex_agent, CODEX_EXT),
        "opencode": (emit_opencode_agent, ".md"),
        "cursor": (emit_cursor_agent, CURSOR_EXT),
    }
    if args.command.startswith("emit-") and targets[0] in emitters:
        target = targets[0]
        emit, extension = emitters[target]
        out_dir = Path(args.out_dir)
        # _sync_dir prunes files a previous emit wrote for agents that are now disabled.
        _sync_dir(out_dir, {f"{a.name}{extension}": emit(a) for a in agents})
        print(f"emitted {len(agents)} {target} agents to {out_dir}")
        return 0

    if args.command == "emit-copilot":
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        content = emit_copilot_instructions(agents)
        (out_dir / "global-agents-instructions.md").write_text(content, encoding="utf-8")
        print(f"emitted copilot instructions ({len(agents)} agents) to {out_dir}")
        return 0

    if args.command == "install":
        home = Path.home()

        if "claude" in targets:
            files = {f"{a.name}.md": emit_claude_agent(a) for a in agents}
            n = _sync_dir(home / ".claude" / "agents", files)
            print(f"installed {n} agents → ~/.claude/agents")

        if "codex" in targets:
            files = {f"{a.name}{CODEX_EXT}": emit_codex_agent(a) for a in agents}
            n = _sync_dir(home / ".codex" / "agents", files)
            print(f"installed {n} agents → ~/.codex/agents (TOML)")

        if "opencode" in targets:
            files = {f"{a.name}.md": emit_opencode_agent(a) for a in agents}
            n = _sync_dir(home / ".config" / "opencode" / "agents", files)
            print(f"installed {n} agents → ~/.config/opencode/agents")

        if "copilot" in targets:
            dest = home / ".config" / "github-copilot"
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "global-agents-instructions.md").write_text(
                emit_copilot_instructions(agents), encoding="utf-8"
            )
            print(f"installed {len(agents)} agents → ~/.config/github-copilot/global-agents-instructions.md")

        if "cursor" in targets:
            files = {f"{a.name}{CURSOR_EXT}": emit_cursor_agent(a) for a in agents}
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
    # Only plain filenames are ours; a tampered manifest must not reach outside dest.
    previously_owned = {
        name for name in previously_owned if isinstance(name, str) and name not in {"", ".", ".."} and Path(name).name == name
    }

    for name, content in files.items():
        (dest / name).write_text(content, encoding="utf-8")

    for stale in previously_owned - set(files):
        target = dest / stale
        if target.resolve().parent == dest.resolve() and target.exists():
            target.unlink()

    manifest_path.write_text(json.dumps(sorted(files), indent=2), encoding="utf-8")
    return len(files)


if __name__ == "__main__":
    raise SystemExit(main())
