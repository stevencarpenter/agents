from __future__ import annotations

from agent_registry.agents import Agent, validate_isolated_read_only, yaml_string
from agent_registry.mcp_tools import parse_tools_field
from agent_registry.model_translation import translate_model

# The filename is the agent name, so `name` is not in the frontmatter.
# mode: all keeps agents visible in the /agents switcher and invocable as subagents.
# permission rules are last-match-wins, so `"*": deny` must precede every grant.

_CLAUDE_TO_OPENCODE_TOOL = {
    "Bash": "bash",
    "Glob": "glob",
    "Grep": "grep",
    "Read": "read",
    "Skill": "skill",
}


def emit_opencode_agent(agent: Agent) -> str:
    validate_isolated_read_only(agent, "opencode")
    description = agent.metadata.get("description", "")
    can_edit = agent.metadata.get("x-registry-permission") == "edit"
    can_bash = agent.metadata.get("x-isolated-read-only") != "true"

    lines = [
        "---",
        f"description: {yaml_string(description)}",
        "mode: all",
    ]

    model = translate_model(agent.metadata.get("model", ""), "opencode")
    if model:
        lines.append(f"model: {model}")

    lines.append("permission:")
    lines.append(f"  edit: {'allow' if can_edit else 'deny'}")
    lines.append(f"  bash: {'allow' if can_bash else 'deny'}")

    if agent.metadata.get("x-allow-tools-allowlist") == "true":
        allowlist = parse_tools_field(agent.metadata.get("tools", ""))
        lines.append('  "*": deny')
        for tool in allowlist.plain_tools:
            translated = _CLAUDE_TO_OPENCODE_TOOL.get(tool)
            if translated:
                lines.append(f"  {translated}: allow")
        for server, tools in sorted(allowlist.mcp_servers.items()):
            if tools is None:
                lines.append(f'  "{server}_*": allow')
            else:
                for tool in sorted(tools):
                    lines.append(f'  "{server}_{tool}": allow')

    lines.extend(
        [
            "---",
            "",
            agent.body.rstrip(),
            "",
        ]
    )
    return "\n".join(lines)
