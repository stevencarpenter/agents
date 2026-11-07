from __future__ import annotations

from agent_registry.agents import Agent, validate_isolated_read_only


def emit_copilot_instructions(agents: list[Agent]) -> str:
    """Copilot has no subagents, so emit one reference file of agent names and triggers."""
    for agent in agents:
        validate_isolated_read_only(agent, "copilot")
    lines = [
        "# Specialist Agent Directory",
        "",
        "The following specialist agents are available. Suggest delegating to the",
        "appropriate agent when the task matches its trigger condition.",
        "",
    ]
    for agent in sorted(agents, key=lambda a: a.name):
        description = agent.metadata.get("description", "")
        lines.append(f"## {agent.name}")
        lines.append("")
        lines.append(description)
        lines.append("")
    return "\n".join(lines)
