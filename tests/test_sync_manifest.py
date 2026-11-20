import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_registry.cli import (
    SyncSelection,
    _load_agents,
    _sync_dir,
    load_sync_selection,
    main,
)


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

    def test_enabled_agent_with_disabled_skill_is_rejected(self) -> None:
        path = self._write_manifest('[skills]\n"rubric" = false\n')
        with self.assertRaisesRegex(ValueError, "alpha -> rubric"):
            _load_agents(
                str(self.root / "agents"),
                str(self.root / "skills"),
                load_sync_selection(path),
            )

    def test_disabled_skill_is_allowed_when_its_agents_are_disabled(self) -> None:
        path = self._write_manifest(
            '[agents]\n"alpha" = false\n"beta" = false\n[skills]\n"rubric" = false\n'
        )
        agents = _load_agents(
            str(self.root / "agents"),
            str(self.root / "skills"),
            load_sync_selection(path),
        )
        self.assertEqual(agents, [])

    def test_unknown_name_is_rejected(self) -> None:
        path = self._write_manifest('[agents]\n"ghost" = false\n')
        with self.assertRaisesRegex(ValueError, "unknown names: \\['ghost'\\]"):
            _load_agents(
                str(self.root / "agents"),
                str(self.root / "skills"),
                load_sync_selection(path),
            )

    def test_machine_config_overrides_manifest(self) -> None:
        path = self._write_manifest('[agents]\n"alpha" = true\n"beta" = true\n')
        overlay = self.root / "overlay.json"
        overlay.write_text('{"agents": {"beta": false}}', encoding="utf-8")
        selection = load_sync_selection(path, overlay)
        self.assertEqual(selection.disabled_agents, frozenset({"beta"}))

    def test_machine_config_unknown_name_is_rejected(self) -> None:
        path = self._write_manifest('[agents]\n"alpha" = true\n')
        overlay = self.root / "overlay.json"
        overlay.write_text('{"agents": {"ghost": false}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unknown names: \\['ghost'\\]"):
            _load_agents(
                str(self.root / "agents"),
                str(self.root / "skills"),
                load_sync_selection(path, overlay),
            )

    def test_missing_machine_config_is_an_error(self) -> None:
        path = self._write_manifest('[agents]\n"alpha" = true\n')
        with self.assertRaisesRegex(ValueError, "machine config not found"):
            load_sync_selection(path, self.root / "absent.json")

    def test_install_applies_machine_config(self) -> None:
        overlay = self.root / "overlay.json"
        overlay.write_text('{"agents": {"beta": false}}', encoding="utf-8")
        install_home = self.root / "home"
        with (
            patch(
                "sys.argv",
                [
                    "agent-registry",
                    "install",
                    "--agents-dir",
                    str(self.root / "agents"),
                    "--skills-dir",
                    str(self.root / "skills"),
                    "--machine-config",
                    str(overlay),
                    "--target",
                    "claude",
                ],
            ),
            patch.object(Path, "home", return_value=install_home),
        ):
            main()
        installed = install_home / ".claude" / "agents"
        self.assertTrue((installed / "alpha.md").exists())
        self.assertFalse((installed / "beta.md").exists())

    def test_install_discovers_the_linked_machine_overlay(self) -> None:
        install_home = self.root / "home"
        skills_overlay = install_home / ".config" / "skills" / "machine" / "personal.json"
        skills_overlay.parent.mkdir(parents=True)
        skills_overlay.write_text("{}", encoding="utf-8")
        agents_overlay = install_home / ".config" / "agents" / "machine" / "personal.json"
        agents_overlay.parent.mkdir(parents=True)
        agents_overlay.write_text('{"agents": {"beta": false}}', encoding="utf-8")
        with (
            patch(
                "sys.argv",
                [
                    "agent-registry",
                    "install",
                    "--agents-dir",
                    str(self.root / "agents"),
                    "--skills-dir",
                    str(self.root / "skills"),
                    "--target",
                    "claude",
                ],
            ),
            patch.object(Path, "home", return_value=install_home),
            patch.dict("os.environ", {"DFM_IDENTITY": ""}),
        ):
            main()
        installed = install_home / ".claude" / "agents"
        self.assertTrue((installed / "alpha.md").exists())
        self.assertFalse((installed / "beta.md").exists())

    def test_emit_removes_pre_manifest_files_for_disabled_agents(self) -> None:
        out = self.root / "out"
        out.mkdir()
        (out / "beta.md").write_text("old emit\n", encoding="utf-8")
        (out / "notes.md").write_text("hand written\n", encoding="utf-8")
        self._write_manifest('[agents]\n"beta" = false\n')
        with patch(
            "sys.argv",
            [
                "agent-registry",
                "emit-claude",
                "--agents-dir",
                str(self.root / "agents"),
                "--skills-dir",
                str(self.root / "skills"),
                "--out-dir",
                str(out),
            ],
        ):
            main()
        self.assertFalse((out / "beta.md").exists())
        self.assertTrue((out / "alpha.md").exists())
        self.assertTrue((out / "notes.md").exists(), "must not touch unowned files")

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
