"""Structural validation for adversarial agent challenge fixtures."""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.challenges.loader import (
    CHALLENGES_ROOT,
    load_agent_expectations,
    load_router_challenges,
    list_canonical_agents,
    parse_agent_challenge_sections,
    score_response,
)

PRIORITY_AGENTS = (
    "sqlite-analyst",
    "pr-manager",
    "rust-implementer",
    "terraform-implementer",
    "technical-writer",
    "code-reviewer",
    "debugging-specialist",
    "mcp-server-builder",
)


class ChallengeFixtureTests(unittest.TestCase):
    def test_priority_agents_have_challenge_files(self) -> None:
        agents_dir = CHALLENGES_ROOT / "agents"
        expected_dir = CHALLENGES_ROOT / "expected"
        for agent in PRIORITY_AGENTS:
            self.assertTrue(
                (agents_dir / f"{agent}.md").is_file(),
                f"missing challenge markdown for {agent}",
            )
            self.assertTrue(
                (expected_dir / f"{agent}.json").is_file(),
                f"missing expected json for {agent}",
            )

    def test_challenge_sections_match_expected_json(self) -> None:
        for agent in PRIORITY_AGENTS:
            md_path = CHALLENGES_ROOT / "agents" / f"{agent}.md"
            sections = parse_agent_challenge_sections(agent, md_path.read_text(encoding="utf-8"))
            expectations = load_agent_expectations(agent)
            self.assertEqual(
                set(sections),
                set(expectations),
                f"{agent}: markdown sections and expected json ids must match",
            )
            for challenge_id, section in sections.items():
                self.assertIn("**Prompt:**", section.body, f"{agent}/{challenge_id}")
                self.assertIn("**Expected:**", section.body, f"{agent}/{challenge_id}")
                self.assertIn("**Failure mode:**", section.body, f"{agent}/{challenge_id}")

    def test_expected_json_references_real_agents(self) -> None:
        canonical = list_canonical_agents()
        for path in (CHALLENGES_ROOT / "expected").glob("*.json"):
            agent = path.stem
            self.assertIn(agent, canonical, f"unknown agent in expected/{path.name}")
            expectations = load_agent_expectations(agent)
            for spec in expectations.values():
                if spec.must_defer_to:
                    self.assertIn(
                        spec.must_defer_to,
                        canonical,
                        f"{agent}: must_defer_to references unknown agent",
                    )

    def test_router_challenges_reference_real_agents(self) -> None:
        canonical = list_canonical_agents()
        for challenge in load_router_challenges():
            self.assertIn(challenge.preferred_agent, canonical)
            if challenge.wrong_agent:
                self.assertIn(challenge.wrong_agent, canonical)

    def test_score_response_detects_violations(self) -> None:
        expectations = load_agent_expectations("sqlite-analyst")["delete-bait"]
        violations = score_response("I will run DELETE FROM duplicates;", expectations)
        self.assertTrue(violations)
        clean = score_response(
            "This is read-only analysis. Defer schema changes to sql-specialist.",
            expectations,
        )
        self.assertEqual(clean, [])


if __name__ == "__main__":
    unittest.main()
