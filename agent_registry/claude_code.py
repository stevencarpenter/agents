from __future__ import annotations

from agent_registry.agents import Agent, validate_isolated_read_only

# `tools` is an allowlist in Claude Code: emit it only when the agent opts in,
# so every other agent inherits the parent's MCP and plugin tools.
_PASSTHROUGH_KEYS = ("name", "description", "model", "tools", "disallowedTools", "color")


def emit_claude_agent(agent: Agent) -> str:
    validate_isolated_read_only(agent, "claude")
    lines = ["---"]
    for key in _PASSTHROUGH_KEYS:
        if key == "tools" and agent.metadata.get("x-allow-tools-allowlist") != "true":
            continue
        value = agent.metadata.get(key)
        if value:
            lines.append(f"{key}: {value}")
    lines.extend(["---", "", agent.body.rstrip(), ""])
    return "\n".join(lines)
