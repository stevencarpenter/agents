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
            "Diátaxis discipline. The response should serve the primary reader task "
            "(tutorial = learning by doing; how-to = a task; explanation = "
            "understanding; reference). Keep short context or examples beside the "
            "operation they clarify; do not require splitting a coherent document. "
            "Penalize unrelated digressions that interrupt the reader, OR author-to-reader "
            "meta-narration ('I'll write this directly', 'before drafting, let me "
            "name the reader') leaking into the deliverable.",
        ),
        _judge(
            "tw_operational_completeness",
            "Operational completeness. For a how-to: prerequisites up front, a "
            "verification step, and a real mechanism (not hand-waving). Require "
            "recovery instructions for state changes whose failure can leave the "
            "reader stuck or lose data, not for every reversible command. "
            "For a tutorial: runs end-to-end from clean state "
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
            "Lakehouse + streaming correctness for the requested pipeline. "
            "Require transactional table formats when updates, concurrency, or "
            "snapshot reads need them; separate layers only for distinct contracts "
            "or consumers. Preserve retained inputs needed for replay, "
            "idempotent/replayable sinks (native guarantees, MERGE on a stable key, "
            "or overwrite-by-partition), and small-file control where relevant. "
            "For stateful streaming, require bounded state, correct event-time "
            "watermarks and lateness policy, and checkpoint/recovery compatibility. "
            "Accept exactly-once claims only with a concrete supporting sink and "
            "checkpoint mechanism. Do not reward unnecessary platform migrations.",
        ),
        _judge(
            "de_ml_skew_safety",
            "ML / feature-store correctness where the task involves training or "
            "features. Point-in-time (as-of) joins so no "
            "feature leaks future information; offline↔online parity via a SINGLE "
            "feature transformation (not two codebases); versioning/reproducibility "
            "of training data + feature code. For RAG, require embedding model, "
            "chunking and source versioning plus refresh that handles additions, "
            "updates and deletions. Penalize training/serving skew, label leakage, "
            "or stale derived data. When neither ML nor RAG is in scope, assess "
            "preservation of downstream contracts without requiring a new ML design.",
        ),
        _judge(
            "de_reliability_currency",
            "Reliability, governance, and cost at the task's scope. Quality "
            "checks need explicit dispositions (drop/quarantine/fail) and must "
            "fail when safe processing is impossible. Persisted pipeline changes "
            "need replay/recovery and retention compatible with reproducibility. "
            "New pipelines or changed data boundaries need classification, "
            "authorized readers, and PII controls; narrow edits must preserve "
            "existing controls. Judge cost and platform choices against actual "
            "workload, deployed-version compatibility, and existing infrastructure. "
            "Do not reward a vendor feature, extra layer, or new framework solely "
            "for being newer; do not require alternatives to a suitable platform "
            "the user already selected.",
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
            "one primary message; necessary evidence stays with its claim and "
            "content supports the slide's title (vertical logic). Unrelated "
            "detail moves to speaker notes or another slide; do not cram it on "
            "the slide or require a split solely for supporting evidence.",
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
