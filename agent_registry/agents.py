from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


class AgentValidationError(ValueError):
    """Raised when an agent definition is unsafe or malformed."""


@dataclass(frozen=True)
class Agent:
    path: Path
    name: str
    metadata: dict[str, str]
    body: str


@dataclass(frozen=True)
class Skill:
    path: Path
    name: str
    metadata: dict[str, str]
    body: str


_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
# Claude Code's built-in subagents (Explore, Plan, ...) match by exact,
# case-sensitive `name`, so overriding one requires reproducing that literal
# name even though it violates the kebab-case convention every other agent
# follows. Keep this set to actual built-in names being overridden, not a
# general escape hatch from the naming convention.
_BUILTIN_OVERRIDE_NAMES = {"Explore"}
# Control characters other than tab (\x09) and newline (\x0a). These are illegal
# in TOML strings, so an agent body containing one would emit a .toml file Codex
# cannot parse. Reject at validation rather than letting an emitter produce
# corrupt output. (\r is normalized to \n on load, so it never reaches here.)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-api\d{2}-[A-Za-z0-9_-]{24,}"),
    re.compile(r"sk-[A-Za-z0-9]{32,}"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{20,}"),
]
_REGISTRY_PERMISSIONS = {"read-only", "edit"}
_READ_ONLY_DENIED_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def load_agent(path: Path) -> Agent:
    text = path.read_text(encoding="utf-8")
    metadata, body = _split_frontmatter(text, path)
    name = metadata.get("name", "")
    return Agent(path=path, name=name, metadata=metadata, body=body)


def load_skill(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    metadata, body = _split_frontmatter(text, path)
    name = metadata.get("name", "")
    return Skill(path=path, name=name, metadata=metadata, body=body)


def validate_agent_tree(root: Path) -> list[Agent]:
    if not root.exists():
        raise AgentValidationError(f"agent tree does not exist: {root}")

    agents = [load_agent(path) for path in sorted(root.glob("*/agent.md"))]
    if not agents:
        raise AgentValidationError(f"no agent definitions found under {root}")

    seen: set[str] = set()
    for agent in agents:
        _validate_agent(agent)
        if agent.name in seen:
            raise AgentValidationError(f"duplicate agent name: {agent.name}")
        seen.add(agent.name)
    return agents


def validate_skill_tree(root: Path) -> list[Skill]:
    if not root.exists():
        raise AgentValidationError(f"skill tree does not exist: {root}")

    skills = [load_skill(path) for path in sorted(root.glob("*/SKILL.md"))]
    if not skills:
        raise AgentValidationError(f"no skill definitions found under {root}")

    seen: set[str] = set()
    for skill in skills:
        _validate_registry_item(
            path=skill.path,
            name=skill.name,
            metadata=skill.metadata,
            body=skill.body,
            expected_parent_name=skill.name,
        )
        if skill.name in seen:
            raise AgentValidationError(f"duplicate skill name: {skill.name}")
        seen.add(skill.name)
    return skills


def agent_skill_refs(agent: Agent) -> list[str]:
    """Return the shared-skill names an agent opts into via its `skills:` field.

    Args:
        agent: The agent whose frontmatter may carry a comma-separated `skills`
            field (e.g. ``skills: technical-writing-guidelines, diagramming-guidelines``).

    Returns:
        The referenced skill names in declared order, empty when none.
    """
    raw = agent.metadata.get("skills", "")
    return [name.strip() for name in raw.split(",") if name.strip()]


# A skill body saying "apply `X`" / "follow `X`" is an inline instruction: the
# named rubric must travel with any agent that inlines the referring skill,
# because skills are composed at emit time and cannot be loaded at runtime.
# The verb window is sentence-bounded ([^.`]) so prose that merely *mentions*
# a skill (routing advice naming agents) is not treated as an instruction.
_SKILL_APPLY_REF_RE = re.compile(
    r"(?i)\b(?:apply(?:ing)?|follow(?:ing|s)?)\b[^.`]{0,60}`([a-z0-9-]+)`"
)


def skill_body_refs(skill: Skill, known_names: set[str]) -> list[str]:
    """Return other skills this skill's body instructs the reader to apply.

    Args:
        skill: The skill whose body to scan.
        known_names: All registered skill names; matches outside this set are
            ignored (backticked identifiers that aren't skills).

    Returns:
        Sorted unique names of skills referenced with apply/follow phrasing,
        excluding the skill itself.
    """
    hits = {
        name
        for name in _SKILL_APPLY_REF_RE.findall(skill.body)
        if name in known_names and name != skill.name
    }
    return sorted(hits)


def validate_skill_closure(agents: list[Agent], skills: list[Skill]) -> None:
    """Enforce the inlining-closure invariant across agents and skills.

    Skills are inlined at emit time, not loaded at runtime, so a skill body
    that says "apply `X-guidelines`" is dead text in the built agent unless
    every agent inlining the referring skill also lists X in its ``skills:``
    field.

    Raises:
        AgentValidationError: Naming the agent, the referring skill, and the
            missing skills when the invariant is violated.
    """
    known_names = {s.name for s in skills}
    required = {s.name: set(skill_body_refs(s, known_names)) for s in skills}
    for agent in agents:
        refs = agent_skill_refs(agent)
        ref_set = set(refs)
        for name in refs:
            missing = required.get(name, set()) - ref_set
            if missing:
                raise AgentValidationError(
                    f"{agent.path}: inlines skill '{name}', whose body instructs "
                    f"applying {sorted(missing)}, but the agent's skills: field "
                    f"does not include them — add them or reword the skill's "
                    f"reference into routing advice"
                )


def compose_agent_with_skills(agent: Agent, skills_by_name: dict[str, Skill]) -> Agent:
    """Inline an agent's referenced shared skills into its body.

    Agents opt in with a ``skills:`` frontmatter field. Each named skill's body
    is appended to the agent body under a delimited appendix, so the rendered
    prompt is self-contained on every emit target — the rubric travels with the
    agent rather than depending on the host loading a separate skill at runtime.
    The ``skills`` key is not an emit passthrough key, so it never appears in
    generated output.

    Args:
        agent: The agent to compose.
        skills_by_name: Map of skill name to ``Skill`` (e.g. from
            ``validate_skill_tree``).

    Returns:
        A new ``Agent`` with the inlined body, or the original agent unchanged
        when it references no skills.

    Raises:
        AgentValidationError: If the agent references a skill that does not exist.
    """
    names = agent_skill_refs(agent)
    if not names:
        return agent

    sections = [agent.body.rstrip()]
    for name in names:
        skill = skills_by_name.get(name)
        if skill is None:
            raise AgentValidationError(f"{agent.path}: references unknown skill '{name}'")
        sections.append(
            f"---\n\n"
            f"# Shared rubric: {skill.name}\n\n"
            f"*Inlined from the `{skill.name}` skill so this rubric travels with "
            f"the agent on every target.*\n\n"
            f"{skill.body.rstrip()}"
        )
    composed_body = "\n\n".join(sections) + "\n"
    return Agent(path=agent.path, name=agent.name, metadata=agent.metadata, body=composed_body)


def _split_frontmatter(text: str, path: Path) -> tuple[dict[str, str], str]:
    # Normalize line endings so CRLF/CR-authored files behave identically and
    # never smuggle a bare \r into emitted TOML/markdown.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---\n"):
        raise AgentValidationError(f"{path}: missing YAML frontmatter")

    try:
        raw_frontmatter, body = text[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise AgentValidationError(f"{path}: unterminated YAML frontmatter") from exc

    metadata: dict[str, str] = {}
    for line_number, line in enumerate(raw_frontmatter.splitlines(), start=2):
        if not line.strip():
            continue
        if ":" not in line:
            raise AgentValidationError(f"{path}:{line_number}: expected key: value")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            raise AgentValidationError(f"{path}:{line_number}: empty metadata key")
        metadata[key] = value
    return metadata, body.lstrip("\n")


def _validate_agent(agent: Agent) -> None:
    _validate_registry_item(
        path=agent.path,
        name=agent.name,
        metadata=agent.metadata,
        body=agent.body,
        expected_parent_name=agent.name,
    )
    _validate_agent_tool_contract(agent)


def _validate_registry_item(
    *,
    path: Path,
    name: str,
    metadata: dict[str, str],
    body: str,
    expected_parent_name: str,
) -> None:
    if not name:
        raise AgentValidationError(f"{path}: missing name")
    if not (_NAME_RE.fullmatch(name) or name in _BUILTIN_OVERRIDE_NAMES):
        raise AgentValidationError(f"{path}: invalid name: {name}")
    if path.parent.name != expected_parent_name:
        raise AgentValidationError(
            f"{path}: directory name must match definition name {name}"
        )

    description = metadata.get("description", "")
    if "Use when" not in description:
        raise AgentValidationError(
            f"{path}: description must include a concrete 'Use when' trigger"
        )

    if not body.strip():
        raise AgentValidationError(f"{path}: body must not be empty")

    combined = "\n".join(
        [*(f"{key}: {value}" for key, value in metadata.items()), body]
    )
    if _CONTROL_CHAR_RE.search(combined):
        raise AgentValidationError(
            f"{path}: contains a disallowed control character (only tab and newline are allowed)"
        )
    for pattern in _SECRET_PATTERNS:
        if pattern.search(combined):
            raise AgentValidationError(f"{path}: contains secret-shaped content")


def _validate_agent_tool_contract(agent: Agent) -> None:
    permission = agent.metadata.get("x-registry-permission", "")
    if permission not in _REGISTRY_PERMISSIONS:
        allowed = ", ".join(sorted(_REGISTRY_PERMISSIONS))
        raise AgentValidationError(
            f"{agent.path}: x-registry-permission must be one of: {allowed}"
        )

    if "tools" in agent.metadata and agent.metadata.get("x-allow-tools-allowlist") != "true":
        raise AgentValidationError(
            f"{agent.path}: tools is a Claude allowlist; use disallowedTools plus "
            "x-registry-permission, or set x-allow-tools-allowlist: true with a review note"
        )

    if permission == "read-only":
        denied = _metadata_csv_set(agent.metadata.get("disallowedTools", ""))
        missing = _READ_ONLY_DENIED_TOOLS - denied
        if missing:
            raise AgentValidationError(
                f"{agent.path}: read-only agents must disallow write tools: "
                f"{', '.join(sorted(missing))}"
            )

def _metadata_csv_set(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}
