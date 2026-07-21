from __future__ import annotations

from agent_registry.agents import Agent

# Claude Code agent.md format is close to the registry source format, but
# `tools` is an allowlist there. Do not emit it unless an agent explicitly
# opts into a reviewed allowlist; ordinary agents should inherit parent
# MCP/plugin tools.
_PASSTHROUGH_KEYS = ("name", "description", "model", "tools", "disallowedTools", "color")


def emit_claude_agent(agent: Agent) -> str:
    lines = ["---"]
    for key in _PASSTHROUGH_KEYS:
        if key == "tools" and agent.metadata.get("x-allow-tools-allowlist") != "true":
            continue
        value = agent.metadata.get(key)
        if value:
            lines.append(f"{key}: {value}")
    lines.extend(["---", "", agent.body.rstrip(), ""])
    return "\n".join(lines)
