"""Domain-specific LLM-judge scorers (MLflow make_judge).

Each scorer rates an output 1-5 against one rubric-derived criterion. They are
the operationalization of the same rubrics the agents inline, so the A/B asks a
fair question: does inlining the rubric move the scores the rubric cares about?

All judges are registered (``.register()``) so they show up in the experiment and
are reusable, per the agent-evaluation skill. They are also returned so the
runner can pass the objects straight to ``mlflow.genai.evaluate``.

Template variables available to instructions: ``{{ inputs }}`` (the dataset
input dict, here ``{"task": ..., "agent": ...}``) and ``{{ outputs }}`` (the
agent's text). See MLflow make_judge docs.
"""

from __future__ import annotations

import os

from mlflow.genai.judges import make_judge

# Strong judge model. make_judge wants a "provider:/model" id. Verify your key
# can call it; override with EVAL_JUDGE_MODEL.
JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "anthropic:/claude-opus-4-8")

_SCALE = (
    "Score 1-5 where 1 = badly fails the criterion and 5 = exemplary. "
    "Judge ONLY the criterion below; ignore unrelated strengths or weaknesses. "
    "Be a discriminating grader — reserve 5 for genuinely excellent work."
)


def _judge(name: str, criterion: str):
    return make_judge(
        name=name,
        instructions=(
            f"You are grading the response to a {{{{ inputs }}}} task.\n\n"
            f"CRITERION — {criterion}\n\n"
            f"Response to grade:\n{{{{ outputs }}}}\n\n{_SCALE}"
        ),
        model=JUDGE_MODEL,
        feedback_value_type=int,
    )


# One list of judges per domain. Names are unique across domains so registration
# in a shared experiment doesn't collide.
SCORERS: dict[str, list] = {
    "technical-writer": [
        _judge(
            "tw_diataxis_discipline",
            "Diátaxis discipline. The response should commit cleanly to ONE mode "
            "(tutorial = learning by doing; how-to = a task; explanation = "
            "understanding; reference) appropriate to the task, and stay in it. "
            "Penalize mode-bleed: a how-to that digresses into background, a "
            "tutorial that stops to explain alternatives, OR author-to-reader "
            "meta-narration ('I'll write this directly', 'before drafting, let me "
            "name the reader') leaking into the deliverable.",
        ),
        _judge(
            "tw_operational_completeness",
            "Operational completeness. For a how-to: prerequisites up front, a "
            "verification step, a rollback/recovery path, and a real mechanism "
            "(not hand-waving). For a tutorial: runs end-to-end from clean state "
            "with a visible early win. For an explainer: states the why and the "
            "rejected alternatives. Reward the structure the chosen mode needs.",
        ),
        _judge(
            "tw_concreteness",
            "Concreteness and runnability. Commands/code/examples are specific, "
            "correctly ordered, and safe; claims are checkable; the piece leads "
            "with the goal and is honest about anything unverified. Penalize "
            "vagueness and filler.",
        ),
    ],
    "data-engineer": [
        _judge(
            "de_lakehouse_streaming",
            "Lakehouse + streaming correctness. Medallion layering, a real table "
            "format (Delta/Iceberg), idempotent/replayable sinks (MERGE on a "
            "stable key, overwrite-by-partition), small-file control, and correct "
            "streaming semantics: event-time watermarks, exactly-once ONLY via an "
            "idempotent checkpointed sink, and explicit late-data handling.",
        ),
        _judge(
            "de_ml_skew_safety",
            "ML / feature-store correctness. Point-in-time (as-of) joins so no "
            "feature leaks future information; offline↔online parity via a SINGLE "
            "feature transformation (not two codebases); versioning/reproducibility "
            "of training data + feature code. Penalize any design that invites "
            "training/serving skew or label leakage.",
        ),
        _judge(
            "de_reliability_currency",
            "Reliability, governance, cost, and 2026 currency. Quality "
            "expectations with explicit dispositions (drop/quarantine/fail), "
            "backfill/replay story, PII/governance, and cost awareness. Reward "
            "current practice (auto-compaction over manual OPTIMIZE, Iceberg REST "
            "catalog / format interop, the VACUUM-vs-time-travel-retention "
            "hazard, declarative streaming tables); penalize dated or vague "
            "advice and unjustified single-vendor lock-in.",
        ),
    ],
    "slide-designer": [
        _judge(
            "sd_storyline_action_titles",
            "Storyline and action titles. Leads with the answer (Pyramid/SCQA); "
            "every slide title is a full-sentence assertion of that slide's "
            "takeaway, not a topic label; reading the titles top-to-bottom tells "
            "the whole story (horizontal logic).",
        ),
        _judge(
            "sd_one_message_per_slide",
            "One message per slide and supporting discipline. Each slide carries "
            "exactly one message; content on a slide proves that slide's title "
            "(vertical logic); detail is pushed to speaker notes, not crammed on "
            "the slide.",
        ),
        _judge(
            "sd_audience_fit",
            "Audience and format fit. The deck is tailored to the stated audience "
            "and time budget, makes a deliberate format/visual choice where "
            "relevant, and uses charts/diagrams to serve a message rather than "
            "decorate.",
        ),
    ],
}


def register_all(experiment_id: str | None = None) -> dict[str, list]:
    """Register every domain's judges and return the registered scorer objects.

    Args:
        experiment_id: MLflow experiment to register into. If None, the active
            experiment is used.

    Returns:
        Domain -> list of registered scorer objects, ready for evaluate().
    """
    registered: dict[str, list] = {}
    for domain, judges in SCORERS.items():
        registered[domain] = [j.register(experiment_id=experiment_id) for j in judges]
    return registered
