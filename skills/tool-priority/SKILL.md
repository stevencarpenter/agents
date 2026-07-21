---
name: tool-priority
description: Use when choosing between skills, MCP/LSP/code-intelligence tools, specialized agents, and built-in file or shell tools.
---

# Tool Priority

Use configured agent tooling before built-in fallbacks.

- Invoke relevant skills before starting task work when the runtime exposes a skill tool.
- Use `ToolSearch` or the runtime's equivalent discovery tool before assuming deferred tools are unavailable.
- Prefer semantic project tools for project understanding: IDEA/IntelliJ MCP, LSP, codegraph, and other MCP servers for file reads, search, symbol lookup, diagnostics, and dependency tracing.
- Use specialized agents or teams for independent workstreams when the runtime exposes them and the task naturally splits.
- Use built-in file tools only after the configured semantic tool is unavailable, not applicable, or too narrow for the artifact type.
- Use `Bash` for repo-native gates, tests, build commands, CLIs, git inspection, and runtime proof. Do not use it as a substitute for semantic search/read tools.
- If this agent is read-only, do not mutate files through shell commands even when a shell tool is available.

When reporting results, mention the exact proof command or semantic tool used for the claim.
