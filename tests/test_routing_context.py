import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "routing"))

import generate_context as gc  # noqa: E402


class RoutingContextTests(unittest.TestCase):
    def test_is_obvious_pair_detects_implementer_reviewer(self) -> None:
        self.assertTrue(gc._is_obvious_pair(["python-implementer", "python-reviewer"]))
        self.assertTrue(gc._is_obvious_pair(["rust-implementer", "rust-idiom-reviewer"]) is False)

    def test_is_obvious_pair_rejects_cross_family(self) -> None:
        self.assertFalse(gc._is_obvious_pair(["data-engineer", "documentation-writer"]))
        self.assertFalse(gc._is_obvious_pair(["sql-specialist", "sqlite-analyst"]))

    def test_is_obvious_pair_requires_exactly_two(self) -> None:
        self.assertFalse(gc._is_obvious_pair(["python-implementer"]))
        self.assertFalse(
            gc._is_obvious_pair(["python-implementer", "python-reviewer", "typescript-implementer"])
        )

    def test_skill_sharers_drops_obvious_pairs_and_skip_families(self) -> None:
        agents = {
            "python-implementer": {"skills": ["python-guidelines"]},
            "python-reviewer": {"skills": ["python-guidelines"]},
            "data-engineer": {"skills": ["diagramming-guidelines", "spark-guidelines"]},
            "slide-designer": {"skills": ["diagramming-guidelines"]},
            "spark-scala-implementer": {"skills": ["spark-guidelines"]},
        }
        result = gc.skill_sharers(agents)
        self.assertNotIn("python-guidelines", result, "obvious implementer/reviewer pair must be dropped")
        self.assertNotIn("spark-guidelines", result, "SKIP_SKILL_FAMILIES entries must be dropped")
        self.assertEqual(result["diagramming-guidelines"], ["data-engineer", "slide-designer"])

    def test_deep_merge_overlay_disables_entry(self) -> None:
        base = {"a": {"enabled": True}, "b": {"x": 1}}
        overlay = {"a": False, "b": {"y": 2}}
        merged = gc.deep_merge(base, overlay)
        self.assertEqual(merged["a"], False)
        self.assertEqual(merged["b"], {"x": 1, "y": 2})

    def test_render_omits_absent_optional_sections(self) -> None:
        # Point every source at a tmp dir that has nothing in it: the
        # generator must degrade to a minimal, still-valid block rather than
        # erroring, matching the "best-effort on a machine without dotfiles
        # applied" design goal.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            gc.AGENTS_REPO = tmp_path / "no-agents-repo"
            gc.INSTALLED_AGENTS_DIR = tmp_path / "no-installed-agents"
            gc.INSTALLED_SKILLS_DIR = tmp_path / "no-installed-skills"
            gc.CLAUDE_JSON = tmp_path / "no-claude.json"
            gc.CHEZMOI_SRC = tmp_path / "no-chezmoi"
            gc.MACHINES_TOML = gc.CHEZMOI_SRC / ".chezmoidata" / "machines.toml"
            gc.SKILLS_MASTER = gc.CHEZMOI_SRC / "dot_config" / "skills" / "skills-master.json"
            gc.SKILLS_MACHINE_DIR = gc.CHEZMOI_SRC / "dot_config" / "skills" / "machine"

            output = gc.render()
            self.assertIn("agent-routing v2", output)
            self.assertNotIn("STALE", output)
            self.assertNotIn("MCP servers", output)

    def test_live_mcp_servers_reads_claude_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            claude_json = Path(tmp) / "claude.json"
            claude_json.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "hippo": {"type": "stdio", "command": "uv"},
                            "idea": {"type": "sse", "url": "http://127.0.0.1:1/sse"},
                        }
                    }
                )
            )
            gc.CLAUDE_JSON = claude_json
            servers = gc.live_mcp_servers()
            self.assertEqual(servers["hippo"], "stdio:uv")
            self.assertEqual(servers["idea"], "sse:http://127.0.0.1:1/sse")


if __name__ == "__main__":
    unittest.main()
