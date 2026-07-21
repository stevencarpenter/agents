from __future__ import annotations

from agent_registry.agents import Agent


def emit_copilot_instructions(agents: list[Agent]) -> str:
    """Emit a global agents instruction file for GitHub Copilot.

    Copilot doesn't have native subagents, so this writes a consolidated
    reference that describes each specialist agent and when to suggest it.
    """
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
