"""Load and validate adversarial challenge fixtures for agent stress tests."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

CHALLENGES_ROOT = Path(__file__).resolve().parent
AGENTS_DIR = CHALLENGES_ROOT.parent.parent / "agents"

_CHALLENGE_HEADING = re.compile(r"^##\s+(?P<id>[a-z0-9-]+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ChallengeSection:
    """One adversarial scenario parsed from an agent challenge markdown file."""

    agent: str
    challenge_id: str
    body: str


@dataclass(frozen=True)
class ChallengeExpectations:
    """Expected response constraints for a single challenge."""

    challenge_id: str
    must_include: tuple[str, ...]
    must_not_include: tuple[str, ...]
    must_defer_to: str | None


@dataclass(frozen=True)
class RouterChallenge:
    """Routing fixture: which agent should own a prompt."""

    challenge_id: str
    prompt: str
    preferred_agent: str
    wrong_agent: str | None
    must_include: tuple[str, ...]
    must_not_include: tuple[str, ...]


def list_canonical_agents() -> frozenset[str]:
    """Return agent names discovered under ``agents/*/agent.md``.

    Returns:
        Frozenset of canonical agent directory names.
    """
    return frozenset(path.parent.name for path in AGENTS_DIR.glob("*/agent.md"))


def parse_agent_challenge_sections(agent: str, text: str) -> dict[str, ChallengeSection]:
    """Parse ``## challenge-id`` sections from an agent challenge markdown file.

    Args:
        agent: Canonical agent name (directory name under ``agents/``).
        text: Full markdown file contents.

    Returns:
        Mapping of challenge id to parsed section.
    """
    headings = list(_CHALLENGE_HEADING.finditer(text))
    sections: dict[str, ChallengeSection] = {}
    for index, match in enumerate(headings):
        challenge_id = match.group("id")
        start = match.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        sections[challenge_id] = ChallengeSection(
            agent=agent,
            challenge_id=challenge_id,
            body=text[start:end].strip(),
        )
    return sections


def load_agent_expectations(agent: str) -> dict[str, ChallengeExpectations]:
    """Load ``expected/<agent>.json`` expectations.

    Args:
        agent: Canonical agent name.

    Returns:
        Mapping of challenge id to expectations.

    Raises:
        FileNotFoundError: When the expected JSON file is missing.
        ValueError: When the JSON shape is invalid.
    """
    path = CHALLENGES_ROOT / "expected" / f"{agent}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "challenges" not in raw:
        raise ValueError(f"{path}: expected top-level 'challenges' mapping")

    expectations: dict[str, ChallengeExpectations] = {}
    for challenge_id, spec in raw["challenges"].items():
        if not isinstance(spec, dict):
            raise ValueError(f"{path}: challenge {challenge_id!r} must be a mapping")
        expectations[challenge_id] = ChallengeExpectations(
            challenge_id=challenge_id,
            must_include=tuple(spec.get("must_include", [])),
            must_not_include=tuple(spec.get("must_not_include", [])),
            must_defer_to=spec.get("must_defer_to"),
        )
    return expectations


def load_router_challenges() -> list[RouterChallenge]:
    """Load routing adversarial fixtures from ``router/*.json``.

    Returns:
        List of router challenge definitions.
    """
    router_dir = CHALLENGES_ROOT / "router"
    challenges: list[RouterChallenge] = []
    for path in sorted(router_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "challenges" not in raw:
            raise ValueError(f"{path}: expected top-level 'challenges' list")
        for item in raw["challenges"]:
            challenges.append(
                RouterChallenge(
                    challenge_id=item["id"],
                    prompt=item["prompt"],
                    preferred_agent=item["preferred_agent"],
                    wrong_agent=item.get("wrong_agent"),
                    must_include=tuple(item.get("must_include", [])),
                    must_not_include=tuple(item.get("must_not_include", [])),
                )
            )
    return challenges


def score_response(response: str, expectations: ChallengeExpectations) -> list[str]:
    """Return violation messages when *response* fails expectations.

    Args:
        response: Agent response text to score (case-insensitive substring match).
        expectations: Required phrases and forbidden phrases.

    Returns:
        Empty list when all constraints pass; otherwise human-readable violations.
    """
    lowered = response.lower()
    violations: list[str] = []
    for phrase in expectations.must_include:
        if phrase.lower() not in lowered:
            violations.append(f"missing required phrase: {phrase!r}")
    for phrase in expectations.must_not_include:
        if phrase.lower() in lowered:
            violations.append(f"forbidden phrase present: {phrase!r}")
    if expectations.must_defer_to and expectations.must_defer_to.lower() not in lowered:
        violations.append(f"missing deferral to specialist: {expectations.must_defer_to!r}")
    return violations
