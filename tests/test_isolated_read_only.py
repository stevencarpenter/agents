import fnmatch
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_registry.agents import Agent, AgentValidationError, validate_isolated_read_only
from agent_registry.claude_code import emit_claude_agent
from agent_registry.cli import main
from agent_registry.codex import emit_codex_agent
from agent_registry.copilot import emit_copilot_instructions
from agent_registry.cursor import emit_cursor_agent
from agent_registry.opencode import emit_opencode_agent


def isolated_agent(**overrides: str) -> Agent:
    metadata = {
        "name": "snapshot-reader",
        "description": "Use when reading supplied evidence.",
        "x-registry-permission": "read-only",
        "x-isolated-read-only": "true",
        "x-allow-tools-allowlist": "true",
        "tools": "Read, Glob, Grep",
        "disallowedTools": "Write, Edit, MultiEdit, NotebookEdit, Bash, Agent, Task",
        **overrides,
    }
    return Agent(Path("agents/snapshot-reader/agent.md"), "snapshot-reader", metadata, "Read only.")


class IsolatedReadOnlyTests(unittest.TestCase):
    def test_rejects_missing_empty_and_unsafe_tool_grants(self):
        for tools in ("", "*", "Read, Bash", "Read, Agent", "Read, Task", "Read, Skill",
                      "Read, ToolSearch", "Read, WebFetch", "Read, Write", "Read, Edit",
                      "Read, mcp__service__get", "Read, mcp__service__*", "Read, browser"):
            with self.subTest(tools=tools), self.assertRaises(AgentValidationError):
                validate_isolated_read_only(isolated_agent(tools=tools))
        for field, value in (("x-registry-permission", "edit"),
                             ("x-allow-tools-allowlist", "false"),
                             ("x-isolated-read-only", "false")):
            with self.subTest(field=field), self.assertRaises(AgentValidationError):
                validate_isolated_read_only(isolated_agent(**{field: value}))
        for field in ("tools", "x-registry-permission", "x-allow-tools-allowlist"):
            agent = isolated_agent()
            del agent.metadata[field]
            with self.subTest(missing=field), self.assertRaises(AgentValidationError):
                validate_isolated_read_only(agent)

    def test_claude_grants_only_local_readers(self):
        output = emit_claude_agent(isolated_agent())
        tools = next(line for line in output.splitlines() if line.startswith("tools:"))
        self.assertEqual(tools, "tools: Read, Glob, Grep")

    def test_opencode_default_denies_mutations_and_indirect_access(self):
        output = emit_opencode_agent(isolated_agent())
        rules = [tuple(part.strip().strip('"') for part in line.split(":", 1))
                 for line in output.splitlines() if line.startswith("  ")]
        # OpenCode uses the last matching rule, including the wildcard default.
        for tool in ("read", "glob", "grep", "bash", "edit", "write", "task", "skill",
                     "webfetch", "browser", "mcp__service__get", "service_add",
                     "service_drop", "service_trade", "service_claim", "service_lineup",
                     "new_future_tool"):
            matches = [action for pattern, action in rules if fnmatch.fnmatchcase(tool, pattern)]
            with self.subTest(tool=tool):
                self.assertTrue(matches)
                self.assertEqual(matches[-1], "allow" if tool in {"read", "glob", "grep"} else "deny")

    def test_every_emitter_validates_policy_even_when_called_directly(self):
        emitters = (emit_claude_agent, emit_opencode_agent, emit_codex_agent,
                    emit_cursor_agent, lambda agent: emit_copilot_instructions([agent]))
        for emit in emitters:
            with self.subTest(emit=emit), self.assertRaises(AgentValidationError):
                emit(isolated_agent(tools="Read, Bash"))
        for emit in emitters[2:]:
            with self.subTest(emit=emit), self.assertRaisesRegex(AgentValidationError, "export refused"):
                emit(isolated_agent())

    def test_cli_refuses_unsupported_targets_before_any_writes(self):
        commands = [["emit-" + target] for target in ("codex", "cursor", "copilot")]
        commands += [["install", "--target", target] for target in ("all", "codex", "cursor", "copilot")]
        for command in commands:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                argv = ["agent-registry", *command]
                if command[0].startswith("emit-"):
                    argv += ["--out-dir", str(root / "output")]
                with patch("sys.argv", argv), patch("pathlib.Path.home", return_value=root), \
                     patch("agent_registry.cli._load_agents", return_value=[isolated_agent()]):
                    with self.assertRaisesRegex(AgentValidationError, "export refused"):
                        main()
                self.assertEqual(list(root.iterdir()), [])
