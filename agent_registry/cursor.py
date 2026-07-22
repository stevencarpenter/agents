from __future__ import annotations

from agent_registry.agents import Agent
from agent_registry.model_translation import translate_model

# Cursor subagents are markdown files in ~/.cursor/agents/<name>.md (Cursor
# also reads .claude/agents/ directly, but we emit its own copy so `model`
# gets translated to a Cursor-real id rather than a Claude alias it may not
# recognize). Frontmatter fields, per Cursor's docs: name, description,
# model, readonly, is_background. `model` accepts `inherit` (default) or a
# specific model id — translated from the registry's Claude-alias vocabulary
# via model_translation.py; `inherit`/unset omits the field.
#
# Cursor subagents have NO per-agent MCP/tool scoping field: subagents inherit
# the parent's tools, while `readonly: true` restricts both writes and MCP
# access. Therefore ordinary read-only agents use `readonly: true`, but agents
# whose purpose requires an MCP allowlist must stay writable at the runtime
# level or they cannot do their job. Their prompt still forbids writes, and the
# emitted body gets a loud notice that this is not an enforced boundary.

CURSOR_EXT = ".md"

_UNSCOPED_TOOLS_NOTICE = (
    "> **Tool-scope notice (Cursor):** Cursor subagents cannot be restricted "
    "to a subset of tools or MCP servers — this agent inherits every tool "
    "and every MCP server available in the parent session. It cannot use "
    "Cursor's read-only mode because that would also block the MCP access "
    "needed for this job. Everything below about which tools to use and not "
    "writing is a request this agent must follow voluntarily, not an enforced "
    "boundary."
)


def emit_cursor_agent(agent: Agent) -> str:
    name = agent.metadata.get("name", "")
    description = agent.metadata.get("description", "")

    lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
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
