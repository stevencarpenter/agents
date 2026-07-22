import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_registry.agents import (
    AgentValidationError,
    load_agent,
    load_skill,
    validate_agent_tree,
    validate_skill_tree,
)
from agent_registry.claude_code import emit_claude_agent
from agent_registry.codex import emit_codex_agent
from agent_registry.cursor import emit_cursor_agent
from agent_registry.mcp_tools import parse_tools_field
from agent_registry.model_translation import translate_model
from agent_registry.opencode import emit_opencode_agent


class AgentRegistryTests(unittest.TestCase):
    def write_agent(self, root: Path, name: str, text: str) -> Path:
        agent_dir = root / "agents" / name
        agent_dir.mkdir(parents=True)
        agent_path = agent_dir / "agent.md"
        agent_path.write_text(text, encoding="utf-8")
        return agent_path

    def write_skill(self, root: Path, name: str, text: str) -> Path:
        skill_dir = root / "skills" / name
        skill_dir.mkdir(parents=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(text, encoding="utf-8")
        return skill_path

    def _sample_agent_text(self, name: str) -> str:
        return f"""---
name: {name}
description: Use when reviewing code changes for correctness risks.
model: inherit
disallowedTools: Write, Edit, MultiEdit, NotebookEdit
color: blue
x-registry-permission: read-only
x-derived-from: hippo-session-1
---

Review code with adversarial attention to behavior.
"""

    def test_load_agent_parses_frontmatter_and_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(Path(tmp), "code-reviewer", self._sample_agent_text("code-reviewer"))
            agent = load_agent(path)

            self.assertEqual(agent.name, "code-reviewer")
            self.assertEqual(agent.metadata["disallowedTools"], "Write, Edit, MultiEdit, NotebookEdit")
            self.assertEqual(agent.metadata["x-registry-permission"], "read-only")
            self.assertEqual(agent.metadata["x-derived-from"], "hippo-session-1")
            self.assertEqual(agent.body, "Review code with adversarial attention to behavior.\n")

    def test_validate_agent_tree_rejects_missing_use_when_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.write_agent(
                Path(tmp),
                "bad-agent",
                "---\nname: bad-agent\ndescription: Reviews code.\n---\n\nBody.\n",
            )
            with self.assertRaisesRegex(AgentValidationError, "Use when"):
                validate_agent_tree(Path(tmp) / "agents")

    def test_validate_agent_tree_rejects_secret_shaped_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.write_agent(
                Path(tmp),
                "leaky-agent",
                "---\nname: leaky-agent\ndescription: Use when proving leak detection works.\n---\n\nToken: sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890\n",
            )
            with self.assertRaisesRegex(AgentValidationError, "secret-shaped"):
                validate_agent_tree(Path(tmp) / "agents")

    def test_validate_rejects_control_characters(self) -> None:
        # A control char (here ESC) would emit invalid TOML for Codex; reject it.
        with tempfile.TemporaryDirectory() as tmp:
            self.write_agent(
                Path(tmp),
                "ctrl-agent",
                "---\nname: ctrl-agent\ndescription: Use when proving control chars are rejected.\n---\n\nBody with an escape: \x1b[0m here.\n",
            )
            with self.assertRaisesRegex(AgentValidationError, "control character"):
                validate_agent_tree(Path(tmp) / "agents")

    def test_validate_agent_tree_rejects_missing_registry_permission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.write_agent(
                Path(tmp),
                "ambiguous-agent",
                "---\nname: ambiguous-agent\ndescription: Use when proving permission validation works.\n---\n\nBody.\n",
            )
            with self.assertRaisesRegex(AgentValidationError, "x-registry-permission"):
                validate_agent_tree(Path(tmp) / "agents")

    def test_validate_agent_tree_rejects_unreviewed_tools_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.write_agent(
                Path(tmp),
                "allowlisted-agent",
                "---\nname: allowlisted-agent\ndescription: Use when proving tools allowlist validation works.\ntools: Read, Bash\nx-registry-permission: read-only\ndisallowedTools: Write, Edit, MultiEdit, NotebookEdit\n---\n\nBody.\n",
            )
            with self.assertRaisesRegex(AgentValidationError, "tools is a Claude allowlist"):
                validate_agent_tree(Path(tmp) / "agents")

    def test_validate_agent_tree_requires_write_denies_for_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.write_agent(
                Path(tmp),
                "readonly-agent",
                "---\nname: readonly-agent\ndescription: Use when proving read-only deny validation works.\nx-registry-permission: read-only\ndisallowedTools: Write, Edit\n---\n\nBody.\n",
            )
            with self.assertRaisesRegex(AgentValidationError, "read-only agents must disallow"):
                validate_agent_tree(Path(tmp) / "agents")

    def test_load_agent_normalizes_crlf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(
                Path(tmp),
                "crlf-agent",
                "---\r\nname: crlf-agent\r\ndescription: Use when proving CRLF is normalized.\r\n---\r\n\r\nLine one.\r\nLine two.\r\n",
            )
            agent = load_agent(path)

            self.assertNotIn("\r", agent.body)
            self.assertEqual(agent.metadata["name"], "crlf-agent")
            # Normalized body emits clean TOML.
            import tomllib

            self.assertNotIn("\r", tomllib.loads(emit_codex_agent(agent))["developer_instructions"])

    # ---- emit-codex (TOML) ----

    def test_emit_codex_agent_emits_toml_with_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(
                Path(tmp),
                "reviewer",
                "---\nname: reviewer\ndescription: Use when reviewing code changes for correctness risks.\nmodel: opus\ndisallowedTools: Write, Edit, MultiEdit, NotebookEdit\ncolor: green\nx-registry-permission: read-only\nx-derived-from: hippo-session-2\n---\n\nReview carefully.\n",
            )
            agent = load_agent(path)
            rendered = emit_codex_agent(agent)

            self.assertIn('name = "reviewer"', rendered)
            self.assertIn('description = "Use when reviewing code changes for correctness risks."', rendered)
            self.assertIn("developer_instructions = '''", rendered)
            self.assertIn("Review carefully.", rendered)
            # Codex TOML must NOT carry markdown frontmatter or Claude-only keys.
            self.assertNotIn("---", rendered)
            self.assertNotIn("tools", rendered)
            self.assertNotIn("color", rendered)
            self.assertNotIn("x-derived-from", rendered)
            # Unknown aliases are omitted so Codex inherits the session model.
            self.assertNotIn("model", rendered)

    def test_emit_codex_translates_haiku_and_enforces_read_only_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(
                Path(tmp),
                "lookup",
                "---\nname: lookup\ndescription: Use when looking up known facts.\nmodel: haiku\nx-registry-permission: read-only\ndisallowedTools: Write, Edit, MultiEdit, NotebookEdit\n---\n\nLook it up.\n",
            )
            rendered = emit_codex_agent(load_agent(path))

            self.assertIn('model = "gpt-5.6-terra"', rendered)
            self.assertIn('sandbox_mode = "read-only"', rendered)

    def test_emit_codex_discloses_unenforced_mcp_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(
                Path(tmp),
                "lookup",
                "---\nname: lookup\ndescription: Use when looking up known facts.\ntools: mcp__docs__fetch\nx-allow-tools-allowlist: true\nx-registry-permission: read-only\ndisallowedTools: Write, Edit, MultiEdit, NotebookEdit\n---\n\nUse only the docs fetch tool.\n",
            )
            rendered = emit_codex_agent(load_agent(path))

            self.assertIn("Tool-scope notice (Codex)", rendered)
            self.assertIn("not an enforced remote-tool boundary", rendered)

    def test_emit_codex_agent_is_parseable_toml(self) -> None:
        import tomllib

        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(Path(tmp), "code-reviewer", self._sample_agent_text("code-reviewer"))
            agent = load_agent(path)
            parsed = tomllib.loads(emit_codex_agent(agent))

            self.assertEqual(parsed["name"], "code-reviewer")
            self.assertTrue(parsed["description"].startswith("Use when"))
            self.assertIn("adversarial attention", parsed["developer_instructions"])

    def test_emit_codex_agent_triple_single_quote_body_roundtrips(self) -> None:
        # Exercises the "" "-fallback path: a body containing ''' cannot use a
        # TOML literal string, so the emitter must escape into a basic string.
        import tomllib

        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(
                Path(tmp),
                "quoter",
                "---\nname: quoter\ndescription: Use when a body contains triple quotes.\n---\n\nUse a Python block: '''docstring''' and a backslash \\d regex.\n",
            )
            agent = load_agent(path)
            rendered = emit_codex_agent(agent)
            parsed = tomllib.loads(rendered)

            self.assertIn("'''docstring'''", parsed["developer_instructions"])
            self.assertIn("\\d regex", parsed["developer_instructions"])

    # ---- emit-claude ----

    def test_emit_claude_agent_denies_writes_without_allowlisting_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(Path(tmp), "code-reviewer", self._sample_agent_text("code-reviewer"))
            agent = load_agent(path)
            rendered = emit_claude_agent(agent)

            self.assertIn("name: code-reviewer\n", rendered)
            self.assertIn("disallowedTools: Write, Edit, MultiEdit, NotebookEdit\n", rendered)
            self.assertNotIn("tools:", rendered)
            self.assertIn("color: blue\n", rendered)
            self.assertIn("model: inherit\n", rendered)
            self.assertNotIn("x-registry-permission:", rendered)
            self.assertNotIn("x-derived-from:", rendered)
            self.assertTrue(rendered.endswith("Review code with adversarial attention to behavior.\n"))

    def test_emit_claude_agent_omits_tools_for_edit_capable_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(
                Path(tmp),
                "implementer",
                "---\nname: implementer\ndescription: Use when implementing code.\nmodel: inherit\nx-registry-permission: edit\n---\n\nWrite code.\n",
            )
            agent = load_agent(path)
            rendered = emit_claude_agent(agent)

            self.assertIn("name: implementer\n", rendered)
            self.assertNotIn("tools:", rendered)
            self.assertNotIn("disallowedTools:", rendered)

    def test_emit_claude_agent_allows_reviewed_tools_escape_hatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(
                Path(tmp),
                "locked-agent",
                "---\nname: locked-agent\ndescription: Use when a reviewed Claude allowlist is required.\ntools: Read, mcp__example__*\nx-allow-tools-allowlist: true\nx-registry-permission: read-only\ndisallowedTools: Write, Edit, MultiEdit, NotebookEdit\n---\n\nInspect with a narrow tool surface.\n",
            )
            agent = load_agent(path)
            rendered = emit_claude_agent(agent)

            self.assertIn("tools: Read, mcp__example__*\n", rendered)
            self.assertNotIn("x-allow-tools-allowlist:", rendered)

    def test_emit_claude_agent_strips_extension_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(Path(tmp), "code-reviewer", self._sample_agent_text("code-reviewer"))
            agent = load_agent(path)
            rendered = emit_claude_agent(agent)

            self.assertNotIn("x-derived-from:", rendered)

    # ---- emit-opencode (native agent, mode: all) ----

    def test_emit_opencode_agent_is_native_agent_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(Path(tmp), "code-reviewer", self._sample_agent_text("code-reviewer"))
            agent = load_agent(path)
            rendered = emit_opencode_agent(agent)

            self.assertIn("mode: all\n", rendered)
            self.assertIn("description:", rendered)
            self.assertIn("permission:", rendered)
            # Reviewer is x-registry-permission: read-only → edit denied, bash allowed.
            self.assertIn("edit: deny", rendered)
            self.assertIn("bash: allow", rendered)
            # The name is carried by the filename, not the frontmatter.
            self.assertNotIn("name:", rendered)
            self.assertNotIn("color:", rendered)
            self.assertIn("Review code with adversarial attention to behavior.\n", rendered)

    def test_emit_opencode_agent_grants_edit_to_implementers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(
                Path(tmp),
                "impl",
                "---\nname: impl\ndescription: Use when implementing code.\nx-registry-permission: edit\n---\n\nWrite code.\n",
            )
            agent = load_agent(path)
            rendered = emit_opencode_agent(agent)

            self.assertIn("edit: allow", rendered)
            self.assertIn("bash: allow", rendered)

    def test_emit_opencode_agent_denies_edit_for_read_only_permission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(
                Path(tmp),
                "lookalike",
                "---\nname: lookalike\ndescription: Use when proving registry permissions drive OpenCode.\nx-registry-permission: read-only\ndisallowedTools: Write, Edit, MultiEdit, NotebookEdit\n---\n\nInspect only.\n",
            )
            agent = load_agent(path)
            rendered = emit_opencode_agent(agent)

            self.assertIn("edit: deny", rendered)
            self.assertIn("bash: allow", rendered)

    def test_emit_opencode_reviewed_allowlist_is_default_deny(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(
                Path(tmp),
                "lookup",
                "---\nname: lookup\ndescription: Use when looking up known facts.\nmodel: haiku\ntools: Read, mcp__docs__resolve, mcp__docs__fetch\nx-allow-tools-allowlist: true\nx-registry-permission: read-only\ndisallowedTools: Write, Edit, MultiEdit, NotebookEdit\n---\n\nLook it up.\n",
            )
            rendered = emit_opencode_agent(load_agent(path))

            deny_index = rendered.index('"*": deny')
            self.assertLess(deny_index, rendered.index("read: allow"))
            self.assertLess(deny_index, rendered.index('"docs_fetch": allow'))
            self.assertIn('"docs_resolve": allow', rendered)
            self.assertIn("model: anthropic/claude-haiku-4-5", rendered)

    # ---- shared translations and Cursor ----

    def test_parse_tools_field_preserves_wildcards_and_specific_tools(self) -> None:
        parsed = parse_tools_field("Read, mcp__one__*, mcp__two__first, mcp__two__second")

        self.assertEqual(parsed.plain_tools, ("Read",))
        self.assertIsNone(parsed.mcp_servers["one"])
        self.assertEqual(parsed.mcp_servers["two"], frozenset({"first", "second"}))

    def test_model_translation_uses_current_target_ids(self) -> None:
        self.assertEqual(translate_model("haiku", "codex"), "gpt-5.6-terra")
        self.assertEqual(translate_model("haiku", "opencode"), "anthropic/claude-haiku-4-5")
        self.assertEqual(translate_model("haiku", "cursor"), "claude-haiku-4-5")
        self.assertIsNone(translate_model("inherit", "codex"))

    def test_emit_cursor_keeps_mcp_agents_functional_and_warns_about_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(
                Path(tmp),
                "lookup",
                "---\nname: lookup\ndescription: Use when looking up known facts.\nmodel: haiku\ntools: mcp__docs__*\nx-allow-tools-allowlist: true\nx-registry-permission: read-only\ndisallowedTools: Write, Edit, MultiEdit, NotebookEdit\n---\n\nLook it up.\n",
            )
            rendered = emit_cursor_agent(load_agent(path))

            self.assertIn("name: lookup\n", rendered)
            self.assertIn("model: claude-haiku-4-5\n", rendered)
            self.assertNotIn("readonly: true\n", rendered)
            self.assertIn("Tool-scope notice (Cursor)", rendered)

    def test_emit_cursor_marks_non_mcp_reviewers_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(Path(tmp), "code-reviewer", self._sample_agent_text("code-reviewer"))

            self.assertIn("readonly: true\n", emit_cursor_agent(load_agent(path)))

    def test_install_cursor_uses_full_agent_set(self) -> None:
        from agent_registry.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_agent(root, "code-reviewer", self._sample_agent_text("code-reviewer"))
            self.write_skill(
                root,
                "unused-skill",
                "---\nname: unused-skill\ndescription: Use when satisfying the fixture skill tree.\n---\n\nFixture.\n",
            )
            install_home = root / "home"
            with (
                patch("sys.argv", ["agent-registry", "install", "--agents-dir", str(root / "agents"), "--skills-dir", str(root / "skills"), "--target", "cursor"]),
                patch.object(Path, "home", return_value=install_home),
            ):
                self.assertEqual(main(), 0)

            self.assertTrue((install_home / ".cursor" / "agents" / "code-reviewer.md").is_file())

    def test_install_copilot_and_all_targets_complete(self) -> None:
        from agent_registry.cli import main

        for target in ("copilot", "all"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.write_agent(root, "code-reviewer", self._sample_agent_text("code-reviewer"))
                self.write_skill(
                    root,
                    "unused-skill",
                    "---\nname: unused-skill\ndescription: Use when satisfying the fixture skill tree.\n---\n\nFixture.\n",
                )
                install_home = root / "home"
                with (
                    patch(
                        "sys.argv",
                        [
                            "agent-registry",
                            "install",
                            "--agents-dir",
                            str(root / "agents"),
                            "--skills-dir",
                            str(root / "skills"),
                            "--target",
                            target,
                        ],
                    ),
                    patch.object(Path, "home", return_value=install_home),
                ):
                    self.assertEqual(main(), 0)

                self.assertTrue(
                    (install_home / ".config" / "github-copilot" / "global-agents-instructions.md").is_file()
                )
                if target == "all":
                    self.assertTrue((install_home / ".claude" / "agents" / "code-reviewer.md").is_file())
                    self.assertTrue((install_home / ".codex" / "agents" / "code-reviewer.toml").is_file())
                    self.assertTrue(
                        (install_home / ".config" / "opencode" / "agents" / "code-reviewer.md").is_file()
                    )
                    self.assertTrue((install_home / ".cursor" / "agents" / "code-reviewer.md").is_file())

    # ---- skill tree ----

    def test_load_skill_parses_frontmatter_and_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_skill(
                Path(tmp),
                "rust-guidelines",
                "---\nname: rust-guidelines\ndescription: Use when writing or reviewing idiomatic Rust.\n---\n\nPrefer strong types and repo-native verification.\n",
            )
            skill = load_skill(path)

            self.assertEqual(skill.name, "rust-guidelines")
            self.assertEqual(skill.body, "Prefer strong types and repo-native verification.\n")

    def test_validate_skill_tree_rejects_missing_use_when_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.write_skill(
                Path(tmp),
                "bad-skill",
                "---\nname: bad-skill\ndescription: Rust guidance.\n---\n\nBody.\n",
            )
            with self.assertRaisesRegex(AgentValidationError, "Use when"):
                validate_skill_tree(Path(tmp) / "skills")

    # ---- presence checks against real agent tree ----

    def test_required_rust_agents_and_skill_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        agents = {agent.name for agent in validate_agent_tree(root / "agents")}
        skills = {skill.name for skill in validate_skill_tree(root / "skills")}

        self.assertEqual(
            {
                "rust-api-designer",
                "rust-async-concurrency-reviewer",
                "rust-idiom-reviewer",
                "rust-implementer",
                "rust-performance-profiler",
                "rust-unsafe-ffi-auditor",
            }
            - agents,
            set(),
        )
        self.assertIn("rust-guidelines", skills)

    def test_language_agents_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        agents = {agent.name for agent in validate_agent_tree(root / "agents")}

        missing = {
            "python-implementer",
            "python-reviewer",
            "typescript-implementer",
            "typescript-reviewer",
            "sql-specialist",
        } - agents
        self.assertEqual(missing, set(), f"missing language agents: {missing}")

    def test_expert_language_agents_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        agents = {agent.name for agent in validate_agent_tree(root / "agents")}

        # Each expert language ships an implementer + reviewer pair.
        expected = {
            f"{lang}-{role}"
            for lang in ("scala", "java", "kotlin", "swift", "terraform")
            for role in ("implementer", "reviewer")
        }
        self.assertEqual(expected - agents, set(), f"missing expert language agents: {expected - agents}")

    def test_spark_agents_and_skills_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        agents = {agent.name for agent in validate_agent_tree(root / "agents")}
        skills = {skill.name for skill in validate_skill_tree(root / "skills")}

        expected_agents = {
            "spark-scala-implementer",
            "spark-scala-reviewer",
            "spark-pyspark-implementer",
            "spark-pyspark-reviewer",
            "spark-streaming-specialist",
            "spark-performance-profiler",
        }
        expected_skills = {
            "spark-guidelines",
            "spark-pyspark-guidelines",
            "spark-scala-guidelines",
        }
        self.assertEqual(
            expected_agents - agents,
            set(),
            f"missing spark agents: {expected_agents - agents}",
        )
        self.assertEqual(
            expected_skills - skills,
            set(),
            f"missing spark skills: {expected_skills - skills}",
        )

    def test_spark_agents_bind_expected_skills(self) -> None:
        from agent_registry.agents import agent_skill_refs

        root = Path(__file__).resolve().parents[1]
        expected = {
            "spark-scala-implementer": [
                "spark-guidelines",
                "spark-scala-guidelines",
                "data-engineering-guidelines",
                "tool-priority",
            ],
            "spark-scala-reviewer": [
                "spark-guidelines",
                "spark-scala-guidelines",
                "data-engineering-guidelines",
                "tool-priority",
            ],
            "spark-pyspark-implementer": [
                "spark-guidelines",
                "spark-pyspark-guidelines",
                "data-engineering-guidelines",
                "tool-priority",
            ],
            "spark-pyspark-reviewer": [
                "spark-guidelines",
                "spark-pyspark-guidelines",
                "data-engineering-guidelines",
                "tool-priority",
            ],
            "spark-performance-profiler": [
                "spark-guidelines",
                "data-engineering-guidelines",
                "tool-priority",
            ],
            "spark-streaming-specialist": [
                "spark-guidelines",
                "spark-scala-guidelines",
                "spark-pyspark-guidelines",
                "data-engineering-guidelines",
                "tool-priority",
            ],
        }
        for agent_name, skill_names in expected.items():
            agent = load_agent(root / "agents" / agent_name / "agent.md")
            self.assertEqual(
                agent_skill_refs(agent),
                skill_names,
                agent_name,
            )

    def test_technology_agents_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        agents = {agent.name for agent in validate_agent_tree(root / "agents")}

        missing = {
            "mcp-server-builder",
            "sqlite-analyst",
            "cli-tool-designer",
            "jj-workflow",
        } - agents
        self.assertEqual(missing, set(), f"missing technology agents: {missing}")

    def test_management_agents_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        agents = {agent.name for agent in validate_agent_tree(root / "agents")}

        missing = {
            "pr-manager",
            "architecture-reviewer",
            "debugging-specialist",
            "documentation-writer",
        } - agents
        self.assertEqual(missing, set(), f"missing management agents: {missing}")

    def test_language_guidelines_skills_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        skills = {skill.name for skill in validate_skill_tree(root / "skills")}

        missing = {
            "rust-guidelines",
            "python-guidelines",
            "typescript-guidelines",
            "sql-guidelines",
            "scala-guidelines",
            "java-guidelines",
            "kotlin-guidelines",
            "swift-guidelines",
            "terraform-guidelines",
        } - skills
        self.assertEqual(missing, set(), f"missing guideline skills: {missing}")

    def test_tool_priority_skill_exists(self) -> None:
        root = Path(__file__).resolve().parents[1]
        skills = {skill.name for skill in validate_skill_tree(root / "skills")}

        self.assertIn("tool-priority", skills)

    def test_real_agents_use_tool_priority_and_no_unreviewed_tools_allowlists(self) -> None:
        root = Path(__file__).resolve().parents[1]
        agents = validate_agent_tree(root / "agents")

        for agent in agents:
            skill_refs = {name.strip() for name in agent.metadata.get("skills", "").split(",") if name.strip()}
            # Mechanical leaf agents (x-mechanical: true) are deliberately exempt: they
            # either carry a hard MCP allowlist that makes tool-priority's advice
            # unreachable, or (Explore) contradict it. See test_mechanical_agents_skip_tool_priority.
            if agent.metadata.get("x-mechanical") != "true":
                self.assertIn("tool-priority", skill_refs, f"{agent.name} must inline tool-priority")
            if "tools" in agent.metadata:
                self.assertEqual(agent.metadata.get("x-allow-tools-allowlist"), "true")

    def test_mechanical_agents_skip_tool_priority(self) -> None:
        """Mechanical leaf agents must NOT inline tool-priority — it is dead weight
        (unreachable under their MCP allowlist) or contradictory (Explore is a leaf
        worker but tool-priority tells agents to spawn teams). This pins that carve-out
        so the rubric is never silently re-added to a pure pass-through agent."""
        from agent_registry.agents import compose_agent_with_skills

        root = Path(__file__).resolve().parents[1]
        skills_by_name = {s.name: s for s in validate_skill_tree(root / "skills")}
        mechanical = [
            a for a in validate_agent_tree(root / "agents")
            if a.metadata.get("x-mechanical") == "true"
        ]
        self.assertTrue(mechanical, "expected at least one x-mechanical agent")
        for agent in mechanical:
            skill_refs = {name.strip() for name in agent.metadata.get("skills", "").split(",") if name.strip()}
            self.assertNotIn("tool-priority", skill_refs, agent.name)
            rendered = emit_claude_agent(compose_agent_with_skills(agent, skills_by_name))
            self.assertNotIn("# Shared rubric: tool-priority", rendered, agent.name)

    def test_real_claude_emits_inherited_tools_shape(self) -> None:
        from agent_registry.agents import compose_agent_with_skills

        root = Path(__file__).resolve().parents[1]
        skills_by_name = {s.name: s for s in validate_skill_tree(root / "skills")}
        agents = validate_agent_tree(root / "agents")

        for agent in agents:
            rendered = emit_claude_agent(compose_agent_with_skills(agent, skills_by_name))
            if agent.metadata.get("x-allow-tools-allowlist") != "true":
                self.assertNotIn("\ntools:", rendered, f"{agent.name} should inherit parent tools")
            if agent.metadata.get("x-registry-permission") == "read-only":
                self.assertIn("disallowedTools: Write, Edit, MultiEdit, NotebookEdit\n", rendered)
            if agent.metadata.get("x-mechanical") != "true":
                self.assertIn("# Shared rubric: tool-priority", rendered)

    # ---- skill inlining (compose) ----

    def test_compose_inlines_referenced_skill_into_body(self) -> None:
        from agent_registry.agents import compose_agent_with_skills

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent_path = self.write_agent(
                root,
                "writer",
                "---\nname: writer\ndescription: Use when writing docs.\nskills: doc-rubric\n---\n\nWrite well.\n",
            )
            self.write_skill(
                root,
                "doc-rubric",
                "---\nname: doc-rubric\ndescription: Use when writing docs well.\n---\n\nLead with the why.\n",
            )
            agent = load_agent(agent_path)
            skills_by_name = {s.name: s for s in validate_skill_tree(root / "skills")}
            composed = compose_agent_with_skills(agent, skills_by_name)

            self.assertIn("Write well.", composed.body)
            self.assertIn("# Shared rubric: doc-rubric", composed.body)
            self.assertIn("Lead with the why.", composed.body)
            # The inlined rubric reaches the emitted Claude agent...
            rendered = emit_claude_agent(composed)
            self.assertIn("Lead with the why.", rendered)
            # ...and the Codex agent body too.
            import tomllib

            parsed = tomllib.loads(emit_codex_agent(composed))
            self.assertIn("Lead with the why.", parsed["developer_instructions"])
            # The build-time `skills:` directive must NOT leak into output frontmatter.
            self.assertNotIn("skills:", rendered)

    def test_compose_is_noop_without_skills_field(self) -> None:
        from agent_registry.agents import compose_agent_with_skills

        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(Path(tmp), "plain", self._sample_agent_text("plain"))
            agent = load_agent(path)
            self.assertIs(compose_agent_with_skills(agent, {}), agent)

    def test_compose_raises_on_unknown_skill(self) -> None:
        from agent_registry.agents import compose_agent_with_skills

        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_agent(
                Path(tmp),
                "dangling",
                "---\nname: dangling\ndescription: Use when referencing a missing skill.\nskills: nope\n---\n\nBody.\n",
            )
            agent = load_agent(path)
            with self.assertRaisesRegex(AgentValidationError, "unknown skill"):
                compose_agent_with_skills(agent, {})

    def test_new_domain_skills_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        skills = {s.name for s in validate_skill_tree(root / "skills")}
        missing = {
            "technical-writing-guidelines",
            "diagramming-guidelines",
            "data-engineering-guidelines",
            "jj-guidelines",
        } - skills
        self.assertEqual(missing, set(), f"missing domain skills: {missing}")

    def test_all_agent_skill_references_resolve(self) -> None:
        # Every `skills:` reference in the real tree must resolve to a real skill.
        from agent_registry.agents import compose_agent_with_skills

        root = Path(__file__).resolve().parents[1]
        agents = validate_agent_tree(root / "agents")
        skills_by_name = {s.name: s for s in validate_skill_tree(root / "skills")}
        for agent in agents:
            compose_agent_with_skills(agent, skills_by_name)  # raises if dangling

    # ---- skill-body closure invariant ----

    def _closure_fixture(self, tmp: Path, agent_skills: str):
        from agent_registry.agents import load_skill as _load_skill

        base = self.write_skill(
            tmp,
            "base-guidelines",
            "---\nname: base-guidelines\ndescription: Use when testing closure.\n---\n\n"
            "For table design, apply `extra-guidelines` throughout.\n",
        )
        extra = self.write_skill(
            tmp,
            "extra-guidelines",
            "---\nname: extra-guidelines\ndescription: Use when testing closure targets.\n---\n\nRules.\n",
        )
        agent = self.write_agent(
            tmp,
            "consumer",
            f"---\nname: consumer\ndescription: Use when testing closure.\nskills: {agent_skills}\n---\n\nBody.\n",
        )
        return [load_agent(agent)], [_load_skill(base), _load_skill(extra)]

    def test_skill_body_refs_detects_apply_instructions(self) -> None:
        from agent_registry.agents import skill_body_refs

        with tempfile.TemporaryDirectory() as tmp:
            _, skills = self._closure_fixture(Path(tmp), "base-guidelines")
            known = {s.name for s in skills}
            base = next(s for s in skills if s.name == "base-guidelines")
            extra = next(s for s in skills if s.name == "extra-guidelines")
            self.assertEqual(skill_body_refs(base, known), ["extra-guidelines"])
            self.assertEqual(skill_body_refs(extra, known), [])

    def test_skill_body_refs_ignores_routing_advice(self) -> None:
        from agent_registry.agents import Skill, skill_body_refs

        skill = Skill(
            path=Path("skills/base-guidelines/SKILL.md"),
            name="base-guidelines",
            metadata={},
            # Mentions a skill without apply/follow phrasing in the same
            # sentence: routing advice, not an inline instruction.
            body=(
                "General style still applies. For non-Spark modules, defer to the "
                "scala-reviewer agent, which carries the full `extra-guidelines` rubric.\n"
            ),
        )
        self.assertEqual(skill_body_refs(skill, {"extra-guidelines"}), [])

    def test_skill_closure_violation_is_rejected(self) -> None:
        from agent_registry.agents import validate_skill_closure

        with tempfile.TemporaryDirectory() as tmp:
            agents, skills = self._closure_fixture(Path(tmp), "base-guidelines")
            with self.assertRaisesRegex(AgentValidationError, "extra-guidelines"):
                validate_skill_closure(agents, skills)

    def test_skill_closure_satisfied_passes(self) -> None:
        from agent_registry.agents import validate_skill_closure

        with tempfile.TemporaryDirectory() as tmp:
            agents, skills = self._closure_fixture(Path(tmp), "base-guidelines, extra-guidelines")
            validate_skill_closure(agents, skills)  # must not raise

    def test_real_tree_satisfies_skill_closure(self) -> None:
        from agent_registry.agents import validate_skill_closure

        root = Path(__file__).resolve().parents[1]
        agents = validate_agent_tree(root / "agents")
        skills = validate_skill_tree(root / "skills")
        validate_skill_closure(agents, skills)

    # ---- install sync/prune ----

    def test_sync_dir_prunes_only_owned_files(self) -> None:
        from agent_registry.cli import _sync_dir

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "agents"
            dest.mkdir()
            user_file = dest / "hand-written.md"
            user_file.write_text("user's own agent", encoding="utf-8")

            _sync_dir(dest, {"a.md": "A", "b.md": "B"})
            self.assertTrue((dest / "a.md").exists())
            self.assertTrue(user_file.exists(), "must not touch hand-written files")

            # Second sync drops b.md; only the previously-owned b.md is pruned.
            _sync_dir(dest, {"a.md": "A2"})
            self.assertEqual((dest / "a.md").read_text(encoding="utf-8"), "A2")
            self.assertFalse((dest / "b.md").exists(), "stale owned file should be pruned")
            self.assertTrue(user_file.exists(), "hand-written file still untouched")


if __name__ == "__main__":
    unittest.main()
