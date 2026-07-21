"""The agents under test, as callable predict functions for MLflow.

The whole point of this harness is an A/B: does inlining a shared skill rubric
into an agent (the `skills:` frontmatter wiring) actually improve output? We
build BOTH variants straight from the registry source so the comparison is
faithful:

- **wired**   = ``compose_agent_with_skills(agent, skills).body`` — the exact
               prompt that gets emitted/deployed (lean body + inlined rubric).
- **unwired** = ``agent.body`` — the lean body only, i.e. the pre-wiring state
               where the rubric reference is a dangling pointer.

A predict function calls the Anthropic API with the variant's body as the system
prompt and the task as the user turn. MLflow auto-traces every call.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import mlflow

# Make the parent `agent_registry` package importable without installing it
# (it is a pure-stdlib uv "virtual project").
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent_registry.agents import (  # noqa: E402  (after sys.path insert)
    compose_agent_with_skills,
    validate_agent_tree,
    validate_skill_tree,
)

# Default model the agents run under. Override with EVAL_AGENT_MODEL.
# NOTE: verify this id is one your ANTHROPIC_API_KEY can call. The deployed
# agents use `model: inherit` (Claude Code's session model, Opus); Sonnet is the
# cheaper default here. Bump to an Opus id for max fidelity to real use.
DEFAULT_AGENT_MODEL = os.environ.get("EVAL_AGENT_MODEL", "claude-sonnet-4-6")

# Applied equally to BOTH variants so it cannot bias the A/B: the API call has no
# tools, so the agent must emit text rather than (e.g.) call the Figma MCP.
_RUNTIME_NOTE = (
    "\n\n---\n(Runtime note: you have no external tools in this environment. "
    "Produce the deliverable directly as your reply; describe any diagram in prose.)"
)

_agents = {a.name: a for a in validate_agent_tree(_REPO_ROOT / "agents")}
_skills = {s.name: s for s in validate_skill_tree(_REPO_ROOT / "skills")}


def system_prompt(agent_name: str, variant: str) -> str:
    """Return the system prompt for an agent in the given variant.

    Args:
        agent_name: Registry agent name, e.g. ``technical-writer``.
        variant: ``"wired"`` (rubric inlined) or ``"unwired"`` (lean body only).

    Returns:
        The system-prompt text, with the neutral runtime note appended.

    Raises:
        KeyError: If the agent name is unknown.
        ValueError: If the variant is not "wired" or "unwired".
    """
    agent = _agents[agent_name]
    if variant == "wired":
        body = compose_agent_with_skills(agent, _skills).body
    elif variant == "unwired":
        body = agent.body
    else:
        raise ValueError(f"unknown variant: {variant!r} (use 'wired' or 'unwired')")
    return body.rstrip() + _RUNTIME_NOTE


def _client():
    """Anthropic SDK client for the configured provider (``EVAL_PROVIDER``).

    - ``anthropic`` (default): direct Anthropic API; needs a *console* key
      (``sk-ant-api03-…``), not a Claude Code OAuth token.
    - ``bedrock``: AWS Bedrock; uses the boto3 credential chain + ``AWS_REGION``.
      Needs the ``bedrock`` extra. Pass a Bedrock model id via ``--agent-model``.
    - ``vertex``: GCP Vertex AI; uses ADC + ``CLOUD_ML_REGION`` /
      ``ANTHROPIC_VERTEX_PROJECT_ID``. Needs the ``vertex`` extra.

    Raises:
        ValueError: If ``EVAL_PROVIDER`` is set to an unrecognized value.
    """
    import anthropic

    provider = os.environ.get("EVAL_PROVIDER", "anthropic").lower()
    if provider == "anthropic":
        return anthropic.Anthropic()
    if provider == "bedrock":
        return anthropic.AnthropicBedrock()
    if provider == "vertex":
        return anthropic.AnthropicVertex()
    raise ValueError(
        f"unknown EVAL_PROVIDER={provider!r} (use 'anthropic', 'bedrock', or 'vertex')"
    )


@mlflow.trace
def run_agent(task: str, agent: str, variant: str, model: str = DEFAULT_AGENT_MODEL) -> str:
    """Run one agent variant against one task and return its text output.

    Args:
        task: The user task prompt.
        agent: Registry agent name (the dataset's ``agent`` input key).
        variant: ``"wired"`` or ``"unwired"``.
        model: Anthropic model id to run the agent under.

    Returns:
        The agent's text reply (concatenated text blocks).
    """
    message = _client().messages.create(
        model=model,
        max_tokens=8192,
        system=system_prompt(agent, variant),
        messages=[{"role": "user", "content": task}],
    )
    return "".join(block.text for block in message.content if block.type == "text")


def make_predict_fn(variant: str, model: str = DEFAULT_AGENT_MODEL):
    """Build an MLflow predict_fn for a variant.

    The returned function's signature is ``(task, agent)`` to match the dataset
    input keys — MLflow calls ``predict_fn(**inputs)``.

    Args:
        variant: ``"wired"`` or ``"unwired"``.
        model: Anthropic model id.

    Returns:
        A callable ``predict_fn(task: str, agent: str) -> str``.
    """

    def predict_fn(task: str, agent: str) -> str:
        return run_agent(task=task, agent=agent, variant=variant, model=model)

    predict_fn.__name__ = f"predict_{variant}"
    return predict_fn
