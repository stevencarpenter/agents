from __future__ import annotations

from agent_registry.agents import Agent

# Codex custom agents are TOML files in ~/.codex/agents/<name>.toml.
# Required fields: name, description, developer_instructions.
# Optional (omitted here so they inherit from the parent session): model,
# model_reasoning_effort, sandbox_mode, mcp_servers, skills.config.
# We do NOT translate Claude model ids (opus/sonnet) to Codex model ids — the
# model field is left out so the agent inherits the session model.

CODEX_EXT = ".toml"


def emit_codex_agent(agent: Agent) -> str:
    name = agent.metadata.get("name", "")
    description = agent.metadata.get("description", "")
    instructions = agent.body.rstrip()

    lines = [
        f"name = {_toml_basic_string(name)}",
        f"description = {_toml_basic_string(description)}",
        f"developer_instructions = {_toml_multiline_string(instructions)}",
        "",
    ]
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
