from __future__ import annotations

from agent_registry.agents import Agent

# OpenCode native agents are markdown files in ~/.config/opencode/agents/<name>.md.
# The filename is the agent name (so `name` is NOT in the frontmatter).
# Frontmatter: description, mode, permission (edit/bash allow|deny).
# The body is the system prompt. model/temperature are omitted to inherit.
#
# mode is `all` (not `subagent`) so each agent both shows up in OpenCode's
# `/agents` switcher (selectable as a primary) AND stays invocable as a
# subagent via @mention / delegation. `subagent`-mode agents are hidden from
# the switcher, which is what made them look "missing" there.


def emit_opencode_agent(agent: Agent) -> str:
    description = agent.metadata.get("description", "")
    can_edit = agent.metadata.get("x-registry-permission") == "edit"
    can_bash = True

    lines = [
        "---",
        f"description: {description}",
        "mode: all",
        "permission:",
        f"  edit: {'allow' if can_edit else 'deny'}",
        f"  bash: {'allow' if can_bash else 'deny'}",
        "---",
        "",
        agent.body.rstrip(),
        "",
    ]
    return "\n".join(lines)
