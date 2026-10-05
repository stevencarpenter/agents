import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "routing"))

import generate_context as gc  # noqa: E402


class RoutingContextTests(unittest.TestCase):
    def test_is_obvious_pair_detects_implementer_reviewer(self) -> None:
        self.assertTrue(gc._is_obvious_pair(["python-implementer", "python-reviewer"]))
        self.assertTrue(gc._is_obvious_pair(["python-reviewer", "python-reviewer"]))
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

    def test_declared_skill_names_apply_machine_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "skills-master.json"
            manifest.write_text(json.dumps({"skills": {"disabled": {}, "retained": {"x": 1}}}))
            (Path(tmp) / "test.json").write_text(
                json.dumps({"skills": {"disabled": False, "added": {}}})
            )
            with mock.patch.multiple(gc, SKILLS_MASTER=manifest, SKILLS_MACHINE_DIR=Path(tmp)):
                self.assertEqual(gc.load_declared_personal_skill_names("test"), {"retained", "added"})

    def test_render_omits_absent_optional_sections(self) -> None:
        # Point every source at a tmp dir that has nothing in it: the
        # generator must degrade to a minimal, still-valid block rather than
        # erroring, matching the "best-effort on a machine without dotfiles
        # applied" design goal.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.multiple(
                gc,
                AGENTS_REPO=tmp_path / "no-agents-repo",
                INSTALLED_AGENTS_DIR=tmp_path / "no-installed-agents",
                INSTALLED_SKILLS_DIR=tmp_path / "no-installed-skills",
                CLAUDE_JSON=tmp_path / "no-claude.json",
                MACHINES_TOML=tmp_path / "no-machines.toml",
                SKILLS_MASTER=tmp_path / "no-skills-master.json",
                SKILLS_MACHINE_DIR=tmp_path / "no-skills-machine",
            ):
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
            with mock.patch.object(gc, "CLAUDE_JSON", claude_json):
                servers = gc.live_mcp_servers()
            self.assertEqual(servers["hippo"], "stdio:uv")
            self.assertEqual(servers["idea"], "sse:http://127.0.0.1:1/sse")


if __name__ == "__main__":
    unittest.main()
