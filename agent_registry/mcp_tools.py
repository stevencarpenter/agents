from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class McpAllowlist:
    """An agent's `tools:` allowlist, split into MCP and non-MCP entries."""

    # Non-MCP tool names verbatim (e.g. "Read").
    plain_tools: tuple[str, ...]
    # server name -> None means every tool from that server (`mcp__server__*`
    # or the bare server-level form `mcp__server`); a set means only those
    # specific tool names.
    mcp_servers: dict[str, frozenset[str] | None]


def parse_tools_field(tools: str) -> McpAllowlist:
    """Parse a Claude-format `tools:` allowlist into plain and MCP entries.

    Recognizes the three Claude Code MCP token shapes: `mcp__server` and
    `mcp__server__*` (both mean "every tool from this server"), and
    `mcp__server__tool_name` (one specific tool).

    Args:
        tools: The raw comma-separated `tools:` frontmatter value.

    Returns:
        The parsed allowlist. Empty when `tools` is blank.
    """
    plain: list[str] = []
    servers: dict[str, frozenset[str] | None] = {}

    for raw_token in tools.split(","):
        token = raw_token.strip()
        if not token:
            continue
        if not token.startswith("mcp__"):
            plain.append(token)
            continue

        rest = token[len("mcp__") :]
        if "__" not in rest:
            servers[rest] = None
            continue

        server, tool = rest.split("__", 1)
        if tool == "*":
            servers[server] = None
            continue

        existing = servers.get(server)
        if existing is None and server in servers:
            continue  # already wildcarded; a specific name adds nothing
        servers[server] = frozenset((existing or frozenset()) | {tool})

    return McpAllowlist(plain_tools=tuple(plain), mcp_servers=servers)
