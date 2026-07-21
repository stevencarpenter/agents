"""Evaluation tasks per domain.

Three domains form a deliberate gradient of expected wiring effect, so the A/B is
interpretable:

- **technical-writer** — lean body; wiring inlines the WHOLE Diátaxis rubric.
  Expect the largest wired↑ delta (mode discipline, no mode-bleed).
- **data-engineer** — medium body; wiring adds the deeper 2026 rubric (Iceberg
  REST catalog, point-in-time joins, VACUUM-vs-retention, drift taxonomy).
  Expect a moderate delta.
- **slide-designer** — its body ALREADY contains the storyline/action-title
  rubric; wiring only adds `diagramming-guidelines`. Acts as a near-zero-delta
  CONTROL: if it shows a big delta, suspect judge noise.

Tasks are self-contained (no repo context needed) and span Diátaxis modes /
design shapes so the rubric's discipline has room to show.
"""

from __future__ import annotations

# Maps each domain to the registry agent that handles it.
AGENT_FOR_DOMAIN = {
    "technical-writer": "technical-writer",
    "data-engineer": "data-engineer",
    "slide-designer": "slide-designer",
}

TASKS: dict[str, list[str]] = {
    "technical-writer": [
        # how-to (incident, task-oriented)
        "Write a how-to guide for rotating a compromised API key in a small "
        "Node.js + PostgreSQL web service on a single VM, with zero downtime. "
        "Audience: a mid-level engineer responding to an incident.",
        # tutorial (learning-oriented — must not bleed into reference/explanation)
        "Write a beginner tutorial that gets someone new to GraphQL to their "
        "first working GraphQL subscription using a tiny Node.js server.",
        # explanation (understanding-oriented — must not become a how-to)
        "Write a conceptual explainer: why a team might choose an event-sourced "
        "architecture over CRUD, with the trade-offs and when NOT to use it.",
        # how-to (config task)
        "Write a how-to guide for adding structured JSON logging to a Python "
        "FastAPI service and shipping the logs to a rotating file.",
        # release notes (tests mode discipline: not a tutorial, not reference)
        "Write the release notes for v2.0 of a CLI tool that renamed three flags "
        "(--out→--output, --v→--verbose, --cfg→--config), dropped Python 3.9 "
        "support, and added a --json output mode.",
    ],
    "data-engineer": [
        "Design a near-real-time pipeline ingesting web clickstream events "
        "(~50M/day) and serving BOTH BI dashboards and an ML feature store on a "
        "lakehouse. Cover ingestion, layer layout, data quality, the "
        "feature-store handoff (avoiding training/serving skew), and recovery.",
        "Design CDC ingestion from an operational PostgreSQL database into a "
        "lakehouse silver layer that maintains SCD type-2 history, with "
        "idempotent replay.",
        "Design the data layer for a RAG system: document ingestion, chunking, "
        "embedding generation, the vector index, and keeping the index fresh as "
        "source documents change.",
        "A streaming job is producing thousands of tiny files and duplicate rows "
        "are showing up in the downstream gold table. Diagnose the likely causes "
        "and design the corrected pipeline.",
        "Design a migration from a nightly batch daily-sales aggregation to a "
        "near-real-time streaming version, keeping the existing BI dashboards "
        "stable throughout the cutover.",
    ],
    "slide-designer": [
        "Produce the slide-by-slide outline (titles + key content per slide) for "
        "a 10-minute internal tech talk: 'Why we replaced nightly batch ETL with "
        "streaming CDC'. Audience: mixed engineering + product.",
        "Outline a design-review deck proposing migrating authentication from "
        "server sessions to JWTs. Audience: senior engineers who will push back.",
        "Outline a 5-slide executive readout on a platform-reliability "
        "initiative (cut Sev-1s by 60%). Audience: VPs, 10 minutes.",
        "Outline a 15-minute conference talk: 'Debugging distributed systems "
        "with distributed tracing'. Audience: practitioners.",
    ],
}
