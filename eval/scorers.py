"""Domain-specific LLM-judge scorers (MLflow make_judge).

Each scorer rates an output 1-5 against one rubric-derived criterion. They are
the operationalization of the same rubrics the agents inline, so the A/B asks a
fair question: does inlining the rubric move the scores the rubric cares about?

All judges are registered (``.register()``) so they show up in the experiment and
are reusable, per the agent-evaluation skill. They are also returned so the
runner can pass the objects straight to ``mlflow.genai.evaluate``.

Judges are built by ``build_scorers(judge_model)`` and not at import, so the
runner's ``--judge-model`` flag decides the model.

Template variables available to instructions: ``{{ inputs }}`` (the dataset
input dict, here ``{"task": ..., "agent": ...}``) and ``{{ outputs }}`` (the
agent's text). See MLflow make_judge docs.
"""

from __future__ import annotations

from mlflow.genai.judges import make_judge

_SCALE = (
    "Score 1-5 where 1 = badly fails the criterion and 5 = exemplary. "
    "Judge ONLY the criterion below; ignore unrelated strengths or weaknesses. "
    "Be a discriminating grader: reserve 5 for genuinely excellent work."
)


def _judge(name: str, criterion: str, model: str):
    return make_judge(
        name=name,
        instructions=(
            f"You are grading the response to a {{{{ inputs }}}} task.\n\n"
            f"CRITERION: {criterion}\n\n"
            f"Response to grade:\n{{{{ outputs }}}}\n\n{_SCALE}"
        ),
        model=model,
        feedback_value_type=int,
    )


# One list of (name, criterion) per domain. Names are unique across domains so
# registration in a shared experiment doesn't collide.
_CRITERIA: dict[str, list[tuple[str, str]]] = {
    "technical-writer": [
        (
            "tw_diataxis_discipline",
            "Diátaxis discipline. The response should serve the primary reader task "
            "(tutorial = learning by doing; how-to = a task; explanation = "
            "understanding; reference). Keep short context or examples beside the "
            "operation they clarify; do not require splitting a coherent document. "
            "Penalize unrelated digressions that interrupt the reader, OR author-to-reader "
            "meta-narration ('I'll write this directly', 'before drafting, let me "
            "name the reader') leaking into the deliverable.",
        ),
        (
            "tw_operational_completeness",
            "Operational completeness. For a how-to: prerequisites up front, a "
            "verification step, and a real mechanism (not hand-waving). Require "
            "recovery instructions for state changes whose failure can leave the "
            "reader stuck or lose data, not for every reversible command. "
            "For a tutorial: runs end-to-end from clean state "
            "with a visible early win. For an explainer: states the why and the "
            "rejected alternatives. Reward the structure the chosen mode needs.",
        ),
        (
            "tw_concreteness",
            "Concreteness and runnability. Commands/code/examples are specific, "
            "correctly ordered, and safe; claims are checkable; the piece leads "
            "with the goal and is honest about anything unverified. Penalize "
            "vagueness and filler.",
        ),
    ],
    "data-engineer": [
        (
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
        (
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
        (
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
        (
            "sd_storyline_action_titles",
            "Storyline and action titles. Leads with the answer (Pyramid/SCQA); "
            "every slide title is a full-sentence assertion of that slide's "
            "takeaway, not a topic label; reading the titles top-to-bottom tells "
            "the whole story (horizontal logic).",
        ),
        (
            "sd_one_message_per_slide",
            "One message per slide and supporting discipline. Each slide carries "
            "one primary message; necessary evidence stays with its claim and "
            "content supports the slide's title (vertical logic). Unrelated "
            "detail moves to speaker notes or another slide; do not cram it on "
            "the slide or require a split solely for supporting evidence.",
        ),
        (
            "sd_audience_fit",
            "Audience and format fit. The deck is tailored to the stated audience "
            "and time budget, makes a deliberate format/visual choice where "
            "relevant, and uses charts/diagrams to serve a message rather than "
            "decorate.",
        ),
    ],
}


def build_scorers(judge_model: str) -> dict[str, list]:
    """Build every domain's judges on one judge model.

    Args:
        judge_model: A make_judge "provider:/model" id.

    Returns:
        Domain -> list of judge objects, ready for evaluate() or register_all().
    """
    return {
        domain: [_judge(name, criterion, judge_model) for name, criterion in criteria]
        for domain, criteria in _CRITERIA.items()
    }


def register_all(
    scorers_by_domain: dict[str, list], experiment_id: str | None = None
) -> dict[str, list]:
    """Register the given judges and return the registered scorer objects.

    Args:
        scorers_by_domain: Domain -> judges, from build_scorers().
        experiment_id: MLflow experiment to register into. If None, the active
            experiment is used.

    Returns:
        Domain -> list of registered scorer objects, ready for evaluate().
    """
    registered: dict[str, list] = {}
    for domain, judges in scorers_by_domain.items():
        registered[domain] = [j.register(experiment_id=experiment_id) for j in judges]
    return registered
