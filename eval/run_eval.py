"""Run the wired-vs-unwired A/B evaluation with MLflow.

For each domain and each variant (unwired, wired) it runs
``mlflow.genai.evaluate`` over that domain's tasks with the domain's registered
judges, then prints and saves a per-scorer wired−unwired delta table.

Usage (from the agent-registry repo root):

    uv run --project eval python eval/run_eval.py            # all domains, both variants
    uv run --project eval python eval/run_eval.py --domains technical-writer --limit 2
    uv run --project eval python eval/run_eval.py --agent-model claude-opus-4-8

Prerequisites: ANTHROPIC_API_KEY set; MLflow >= 3.8; ideally MLFLOW_TRACKING_URI
+ an experiment (a SQL-backed tracking server is needed for scorer registration —
without it the run falls back to passing scorer objects inline, which still works).
See HANDOFF.md.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import mlflow
import pandas as pd

from agents import make_predict_fn  # eval/agents.py (script dir is on sys.path)
from scorers import SCORERS, register_all
from tasks import AGENT_FOR_DOMAIN, TASKS

_OUT = Path(__file__).resolve().parent / "results"


def _resolve_experiment(name: str) -> str | None:
    """Set the active experiment; return its id (None if env already pins one)."""
    if os.environ.get("MLFLOW_EXPERIMENT_ID"):
        return os.environ["MLFLOW_EXPERIMENT_ID"]
    exp = mlflow.set_experiment(name)
    return exp.experiment_id


def _metric_for(metrics: dict, scorer_name: str) -> float | None:
    """Pull a scorer's mean score from an MLflow metrics dict, version-tolerantly."""
    if f"{scorer_name}/mean" in metrics:
        return metrics[f"{scorer_name}/mean"]
    for key, value in metrics.items():
        if key.startswith(scorer_name) and isinstance(value, (int, float)):
            return value
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domains", default=",".join(TASKS), help="comma-separated subset")
    parser.add_argument("--variants", default="unwired,wired")
    parser.add_argument("--limit", type=int, default=0, help="max tasks per domain (0 = all)")
    parser.add_argument("--agent-model", default=os.environ.get("EVAL_AGENT_MODEL", "claude-sonnet-4-6"))
    parser.add_argument("--judge-model", default=os.environ.get("EVAL_JUDGE_MODEL", "anthropic:/claude-opus-4-8"))
    parser.add_argument("--experiment", default="agent-registry-wiring-ab")
    args = parser.parse_args()

    # Propagate model choices so agents.py / scorers.py pick them up at import-use time.
    os.environ["EVAL_AGENT_MODEL"] = args.agent_model
    os.environ["EVAL_JUDGE_MODEL"] = args.judge_model

    domains = [d.strip() for d in args.domains.split(",") if d.strip()]
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    _OUT.mkdir(parents=True, exist_ok=True)

    mlflow.anthropic.autolog()  # trace every agent + judge call
    exp_id = _resolve_experiment(args.experiment)
    print(f"experiment={args.experiment} ({exp_id})  agent_model={args.agent_model}  judge_model={args.judge_model}")

    # Register judges if the backend supports it; otherwise use the objects inline.
    try:
        scorers_by_domain = register_all(experiment_id=exp_id)
        print("registered judges:", {d: [s.name for s in v] for d, v in scorers_by_domain.items()})
    except Exception as exc:  # noqa: BLE001 — backend may not support registration
        print(f"scorer registration unavailable ({type(exc).__name__}: {exc}); using inline scorer objects")
        scorers_by_domain = SCORERS

    rows: list[dict] = []
    for domain in domains:
        agent = AGENT_FOR_DOMAIN[domain]
        tasks = TASKS[domain][: args.limit] if args.limit else TASKS[domain]
        data = [{"inputs": {"task": t, "agent": agent}} for t in tasks]
        per_variant_metrics: dict[str, dict] = {}

        for variant in variants:
            print(f"\n=== {domain} :: {variant} ({len(data)} tasks) ===")
            with mlflow.start_run(run_name=f"{domain}:{variant}"):
                mlflow.set_tags({"domain": domain, "variant": variant, "agent_model": args.agent_model})
                result = mlflow.genai.evaluate(
                    data=data,
                    predict_fn=make_predict_fn(variant, args.agent_model),
                    scorers=scorers_by_domain[domain],
                )
            per_variant_metrics[variant] = result.metrics
            # Persist row-level detail when available.
            table = (result.tables or {}).get("eval_results_table")
            if table is not None:
                pd.DataFrame(table).to_csv(_OUT / f"{domain}__{variant}__rows.csv", index=False)

        # Build the per-scorer comparison for this domain.
        for scorer in scorers_by_domain[domain]:
            name = scorer.name
            entry = {"domain": domain, "scorer": name}
            for variant in variants:
                entry[variant] = _metric_for(per_variant_metrics.get(variant, {}), name)
            if "wired" in entry and "unwired" in entry and None not in (entry["wired"], entry["unwired"]):
                entry["delta(wired-unwired)"] = round(entry["wired"] - entry["unwired"], 3)
            rows.append(entry)

    comparison = pd.DataFrame(rows)
    comparison.to_csv(_OUT / "comparison.csv", index=False)
    (_OUT / "raw_metrics.json").write_text(
        json.dumps(rows, indent=2, default=str), encoding="utf-8"
    )

    print("\n================ A/B COMPARISON (mean scores, 1-5) ================")
    with pd.option_context("display.max_colwidth", 40, "display.width", 160):
        print(comparison.to_string(index=False))
    print(f"\nSaved: {_OUT / 'comparison.csv'} and per-row tables in {_OUT}/")
    print("Open the MLflow UI to inspect traces and the eval_results_table per run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
