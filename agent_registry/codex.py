from __future__ import annotations

from agent_registry.agents import Agent
from agent_registry.model_translation import translate_model

# Codex custom agents are TOML files in ~/.codex/agents/<name>.toml.
# Required fields: name, description, developer_instructions.
# Optional: model, model_reasoning_effort, sandbox_mode, mcp_servers,
# skills.config.
#
# We translate `model:` (see model_translation.py) but deliberately do NOT
# emit `mcp_servers` overrides, even though the field exists: Codex's own
# docs show only one subagent `mcp_servers` example, and it's a *full* server
# definition (command/url), not a sparse override of an already-configured
# server by id. The registry doesn't know the user's local server
# command/args (that's user-local config, not registry data), and guessing
# would risk emitting a malformed table that silently breaks the server for
# that agent rather than merely scoping it. So Codex agents get model-tier
# cost control but session-wide MCP/tool access — same caveat as Cursor.
#
# `sandbox_mode` IS a safe, well-documented, per-agent lever (read-only /
# workspace-write / danger-full-access), so read-only registry agents get
# `sandbox_mode = "read-only"` — real enforcement against file/shell writes,
# even without per-tool MCP scoping.

CODEX_EXT = ".toml"

_UNSCOPED_TOOLS_NOTICE = (
    "Tool-scope notice (Codex): this registry cannot safely translate the "
    "source agent's reviewed Claude tools allowlist into a sparse Codex "
    "mcp_servers override. This agent therefore inherits the parent session's "
    "tools and MCP servers. The read-only sandbox blocks filesystem and shell "
    "writes, but instructions below about using only named MCP tools and not "
    "calling mutating remote tools are behavioral requirements, not an "
    "enforced remote-tool boundary."
)


def emit_codex_agent(agent: Agent) -> str:
    name = agent.metadata.get("name", "")
    description = agent.metadata.get("description", "")
    instructions = agent.body.rstrip()
    if agent.metadata.get("x-allow-tools-allowlist") == "true":
        instructions = f"{_UNSCOPED_TOOLS_NOTICE}\n\n{instructions}"

    lines = [
        f"name = {_toml_basic_string(name)}",
        f"description = {_toml_basic_string(description)}",
        f"developer_instructions = {_toml_multiline_string(instructions)}",
    ]

    model = translate_model(agent.metadata.get("model", ""), "codex")
    if model:
        lines.append(f"model = {_toml_basic_string(model)}")

    if agent.metadata.get("x-registry-permission") == "read-only":
        lines.append(f"sandbox_mode = {_toml_basic_string('read-only')}")

    lines.append("")
    return "\n".join(lines)


def _toml_basic_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_multiline_string(body: str) -> str:
    """Render a TOML multi-line string for an arbitrary agent body.

    Prefer a literal string ('''...''') so backslashes in the body (regex
    examples, lint attributes) are not interpreted. Fall back to a basic
    multi-line string ("\"\"\"...\"\"\"") with escaping if the body itself
    contains a triple single-quote.
    """
    if "'''" not in body:
        # A newline immediately after the opening delimiter is trimmed by TOML,
        # so leading content is preserved by starting on the same line.
        return f"'''\n{body}\n'''"
    escaped = body.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return f'"""\n{escaped}\n"""'
