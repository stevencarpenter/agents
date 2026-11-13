from __future__ import annotations

from agent_registry.agents import Agent, validate_isolated_read_only, yaml_string
from agent_registry.model_translation import translate_model

# Cursor also reads .claude/agents/, but its own copy gets a Cursor-real model id.
# Cursor has no per-agent tool scoping, and readonly: true also blocks MCP, so
# agents with an MCP allowlist stay writable and get a loud notice instead.

CURSOR_EXT = ".md"

_UNSCOPED_TOOLS_NOTICE = (
    "> **Tool-scope notice (Cursor):** Cursor subagents cannot be restricted "
    "to a subset of tools or MCP servers. This agent inherits every tool "
    "and every MCP server available in the parent session. It cannot use "
    "Cursor's read-only mode because that would also block the MCP access "
    "needed for this job. Everything below about which tools to use and not "
    "writing is a request this agent must follow voluntarily, not an enforced "
    "boundary."
)


def emit_cursor_agent(agent: Agent) -> str:
    validate_isolated_read_only(agent, "cursor")
    name = agent.metadata.get("name", "")
    description = agent.metadata.get("description", "")

    lines = [
        "---",
        f"name: {name}",
        f"description: {yaml_string(description)}",
    ]

    model = translate_model(agent.metadata.get("model", ""), "cursor")
    if model:
        lines.append(f"model: {model}")

    has_mcp_allowlist = agent.metadata.get("x-allow-tools-allowlist") == "true"
    if agent.metadata.get("x-registry-permission") == "read-only" and not has_mcp_allowlist:
        lines.append("readonly: true")

    lines.append("---")
    lines.append("")

    body = agent.body.rstrip()
    if has_mcp_allowlist:
        body = f"{_UNSCOPED_TOOLS_NOTICE}\n\n{body}"
    lines.append(body)
    lines.append("")

    return "\n".join(lines)
