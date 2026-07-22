from __future__ import annotations

from agent_registry.agents import Agent
from agent_registry.mcp_tools import parse_tools_field
from agent_registry.model_translation import translate_model

# OpenCode native agents are markdown files in ~/.config/opencode/agents/<name>.md.
# The filename is the agent name (so `name` is NOT in the frontmatter).
# Frontmatter: description, mode, model, permission (edit/bash allow|deny,
# plus per-tool/per-MCP-server wildcard keys). The body is the system prompt.
#
# mode is `all` (not `subagent`) so each agent both shows up in OpenCode's
# `/agents` switcher (selectable as a primary) AND stays invocable as a
# subagent via @mention / delegation. `subagent`-mode agents are hidden from
# the switcher, which is what made them look "missing" there.
#
# `model` is translated from the registry's Claude-alias vocabulary via
# model_translation.py; `inherit`/unset omits the field (OpenCode's own
# documented default).
#
# When an agent opts into a reviewed Claude `tools:` MCP allowlist
# (x-allow-tools-allowlist: true), that's translated into OpenCode's
# `permission` map using its documented wildcard-against-tool-name matching:
# `"server_*": "allow"` for a whole-server grant, `"server_tool": "allow"`
# for a specific tool. OpenCode enables tools by default and applies matching
# rules in order, with the last match winning, so `"*": deny` must precede
# every explicit grant for this to be a real allowlist.

_CLAUDE_TO_OPENCODE_TOOL = {
    "Bash": "bash",
    "Glob": "glob",
    "Grep": "grep",
    "Read": "read",
    "Skill": "skill",
}


def emit_opencode_agent(agent: Agent) -> str:
    description = agent.metadata.get("description", "")
    can_edit = agent.metadata.get("x-registry-permission") == "edit"
    can_bash = True

    lines = [
        "---",
        f"description: {description}",
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
