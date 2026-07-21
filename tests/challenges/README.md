# Adversarial Agent Challenges

Stress-test fixtures for the 34 canonical agents in this repo. Each challenge is a
prompt/scenario designed to probe prompt-following, boundary enforcement, verification
gates, and script utilization.

## Layout

```
tests/challenges/
  agents/<agent>.md       # Human-readable scenarios (Prompt / Expected / Failure mode)
  expected/<agent>.json   # Machine-checkable must_include / must_not_include constraints
  router/*.json           # Cross-agent routing probes
  loader.py               # Parse fixtures and score responses
```

## Running structural validation

```sh
uv run python -m unittest discover -s tests
```

`tests/test_challenges.py` verifies that priority-agent fixtures exist, markdown sections
match expected JSON ids, and deferral targets reference real agents.

## Scoring an agent response (manual or harness)

```python
from tests.challenges.loader import load_agent_expectations, score_response

expectations = load_agent_expectations("sqlite-analyst")["delete-bait"]
violations = score_response(agent_response_text, expectations["delete-bait"])
```

## Adding challenges

1. Add a `## challenge-id` section to `agents/<agent>.md` with **Prompt**, **Expected**,
   and **Failure mode** fields.
2. Mirror the id in `expected/<agent>.json` with `must_include`, `must_not_include`, and
   optional `must_defer_to`.
3. Run `uv run python -m unittest tests.test_challenges -v`.

Priority agents (highest ROI) are listed in `tests/test_challenges.py` as
`PRIORITY_AGENTS`. Expand coverage agent-by-agent from the adversarial stress test report.

## Future work

- Wire a harness that invokes agents and asserts `score_response` passes.
- Add `scripts/collect-gates.sh` to snapshot verification commands from agent frontmatter.
- Chezmoi mini-fixture tree for template-debugger regression without real dotfiles.
