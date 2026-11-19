import tempfile
import unittest
from pathlib import Path

from agent_registry.cli import SyncSelection, _load_agents, _sync_dir, load_sync_selection


def _agent(name: str, skills: str = "") -> str:
    return f"""---
name: {name}
description: Use when testing sync selection for {name}.
x-registry-permission: edit
skills: {skills}
---

Body of {name}.
"""


def _skill(name: str) -> str:
    return f"""---
name: {name}
description: Use when testing inlining of {name}.
---

Rubric body of {name}.
"""


class SyncManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ("alpha", "beta"):
            path = self.root / "agents" / name / "agent.md"
            path.parent.mkdir(parents=True)
            path.write_text(_agent(name, "rubric"), encoding="utf-8")
        skill = self.root / "skills" / "rubric" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(_skill("rubric"), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_manifest(self, text: str) -> Path:
        path = self.root / "sync-manifest.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_missing_manifest_selects_everything(self) -> None:
        self.assertEqual(
            load_sync_selection(self.root / "absent.toml"), SyncSelection()
        )

    def test_false_entries_are_loaded_and_true_entries_are_not(self) -> None:
        path = self._write_manifest(
            '[agents]\n"alpha" = true\n"beta" = false\n'
            '[skills]\n"rubric" = false\n'
        )
        self.assertEqual(
            load_sync_selection(path),
            SyncSelection(frozenset({"beta"}), frozenset({"rubric"})),
        )

    def test_missing_entry_defaults_to_enabled(self) -> None:
        path = self._write_manifest('[agents]\n"alpha" = true\n')
        self.assertEqual(load_sync_selection(path), SyncSelection())

    def test_non_boolean_value_is_rejected(self) -> None:
        path = self._write_manifest('[agents]\n"beta" = "false"\n')
        with self.assertRaisesRegex(ValueError, "must be true or false"):
            load_sync_selection(path)

    def test_disabled_agent_is_not_installed_but_still_validates(self) -> None:
        path = self._write_manifest('[agents]\n"beta" = false\n')
        selection = load_sync_selection(path)
        agents_dir = str(self.root / "agents")
        skills_dir = str(self.root / "skills")
        active = [a.name for a in _load_agents(agents_dir, skills_dir, selection)]
        self.assertEqual(active, ["alpha"])
        # validate runs from the same checkout; a disabled file stays in the tree.
        self.assertEqual(
            len(_load_agents(agents_dir, skills_dir, selection, apply=False)), 2
        )

    def test_disabled_skill_is_not_inlined(self) -> None:
        path = self._write_manifest('[skills]\n"rubric" = false\n')
        agents = _load_agents(
            str(self.root / "agents"),
            str(self.root / "skills"),
            load_sync_selection(path),
        )
        self.assertEqual(len(agents), 2)
        self.assertTrue(all("Rubric body" not in a.body for a in agents))

    def test_unknown_name_is_rejected(self) -> None:
        path = self._write_manifest('[agents]\n"ghost" = false\n')
        with self.assertRaisesRegex(ValueError, "unknown names: \\['ghost'\\]"):
            _load_agents(
                str(self.root / "agents"),
                str(self.root / "skills"),
                load_sync_selection(path),
            )

    def test_unknown_enabled_name_is_rejected(self) -> None:
        path = self._write_manifest('[agents]\n"ghost" = true\n')
        with self.assertRaisesRegex(ValueError, "unknown names: \\['ghost'\\]"):
            _load_agents(
                str(self.root / "agents"),
                str(self.root / "skills"),
                load_sync_selection(path),
            )

    def test_emit_prunes_agent_disabled_after_earlier_emit(self) -> None:
        out = self.root / "out"
        agents_dir, skills_dir = str(self.root / "agents"), str(self.root / "skills")
        files = lambda agents: {f"{a.name}.md": a.body for a in agents}
        _sync_dir(out, files(_load_agents(agents_dir, skills_dir)))
        self.assertTrue((out / "beta.md").exists())
        selection = load_sync_selection(self._write_manifest('[agents]\n"beta" = false\n'))
        _sync_dir(out, files(_load_agents(agents_dir, skills_dir, selection)))
        self.assertFalse((out / "beta.md").exists())
        self.assertTrue((out / "alpha.md").exists())

    def test_sync_dir_ignores_manifest_entries_outside_dest(self) -> None:
        out = self.root / "out"
        out.mkdir()
        victim = self.root / "victim.txt"
        victim.write_text("keep", encoding="utf-8")
        (out / ".installed-by-agent-registry.json").write_text(
            '["../victim.txt", "..", "sub/x.md"]', encoding="utf-8"
        )
        _sync_dir(out, {"a.md": "a"})
        self.assertTrue(victim.exists())


if __name__ == "__main__":
    unittest.main()
