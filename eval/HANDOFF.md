# Agent wiring A/B evaluation — handoff

**What this answers:** does inlining a shared-skill rubric into an agent (the
`skills:` frontmatter wiring) measurably improve its output, versus the same
agent *without* the rubric? This replaces the earlier n=1 smoke test with a real
MLflow eval (multiple tasks/domain, registered LLM judges, traced runs).

**Requirements:** `ANTHROPIC_API_KEY`, MLflow, and access to the configured
models. Evaluation calls can incur provider charges.

---

## The experiment

Two variants of each agent, both built straight from this repo's source so the
comparison is faithful (see `agents.py`):

| Variant | System prompt | = |
|---|---|---|
| **wired** | `compose_agent_with_skills(agent, skills).body` | exactly what gets deployed (lean body + inlined rubric) |
| **unwired** | `agent.body` | the lean body only — the pre-wiring dangling-reference state |

Three domains form a **deliberate gradient** so results are interpretable:

| Domain | Body | Expected wiring effect | Role |
|---|---|---|---|
| `technical-writer` | lean | **large** — inlines the whole Diátaxis rubric | high-signal |
| `data-engineer` | medium | **moderate** — adds the deeper 2026 rubric | mid-signal |
| `slide-designer` | already fat (rubric in body) | **~none** — only adds `diagramming-guidelines` | **control** |

If `slide-designer` shows a big delta, suspect judge noise — it's the control.

Judges (`scorers.py`) are `make_judge` LLM scorers that operationalize the same
rubric criteria the agents inline (3 per domain, scored 1–5). Same dataset + same
judges for both variants → the only difference is the rubric.

---

## Prerequisites

1. **Python 3.12** (pinned via `eval/.python-version`; `uv` honors it). Do *not* run
   on free-threaded CPython 3.14 — mlflow's `server` entrypoint imports `Traversable`
   from `importlib.abc`, which 3.14 removed, so `mlflow server` crashes on startup
   (and 3.14t also spams pandas GIL warnings). If `uv` ever resolves to 3.14, delete
   `eval/.venv` and re-run `uv sync --project eval`.
2. **Anthropic key — a *console* API key (`sk-ant-api03-…`), NOT a Claude Code OAuth
   token (`sk-ant-oat01-…`).** `export ANTHROPIC_API_KEY=...` (used by agents *and*
   judges). The Messages API rejects an `oat01` token with `401 invalid x-api-key`.
   This is pay-as-you-go API billing, **separate from any Claude subscription** — get
   a key and credits at console.anthropic.com.
3. **MLflow ≥ 3.8** (3.14.0 verified on Python 3.12). A SQL-backed tracking server is
   *optional*: it lets judges be *registered*; without it the run falls back to inline
   scorer objects (verified — works fine, no server needed). If you do want the UI:
   ```sh
   # NOTE: on macOS port 5000 is taken by ControlCenter (AirPlay) — use 5050.
   uv run --project eval mlflow server \
     --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5050
   export MLFLOW_TRACKING_URI=http://127.0.0.1:5050
   ```
4. Copy `eval/.env.example` → `eval/.env` (gitignored) and fill it in, or export
   the vars. **Verify the model ids** are callable by your key (`EVAL_AGENT_MODEL`,
   `EVAL_JUDGE_MODEL`) — defaults are best-guess current ids and may need a date
   suffix or a bump to Opus.

---

## Run

```sh
cd ~/.local/share/agent-registry

# Smoke test first — cheapest possible (1 task, the high-signal domain):
uv run --project eval python eval/run_eval.py --domains technical-writer --limit 1

# Full A/B (all 3 domains, both variants, all tasks ≈ 14 tasks × 2 variants
# agent calls + 3 judges each):
uv run --project eval python eval/run_eval.py

# Higher fidelity to real use (agents run on Opus like Claude Code does):
uv run --project eval python eval/run_eval.py --agent-model claude-opus-4-8
```

### Running with Bedrock or Vertex

If your environment has AWS Bedrock or GCP Vertex access with Claude
enabled, run the agents through those creds instead — the judges too, via a
`bedrock:/…` / `vertex_ai:/…` judge URI. Only the agent *client* changes
(`EVAL_PROVIDER`); the judge change is pure env config.

```sh
uv sync --project eval --extra bedrock          # or: --extra vertex
EVAL_PROVIDER=bedrock \
EVAL_AGENT_MODEL=anthropic.claude-opus-4-<...>-v1:0 \
EVAL_JUDGE_MODEL=bedrock:/anthropic.claude-opus-4-<...>-v1:0 \
  uv run --project eval python eval/run_eval.py
```

`EVAL_PROVIDER` picks the agent client (`anthropic` default / `bedrock` / `vertex`);
an unknown value fails fast. Verify the exact model id / inference-profile for your
region — Bedrock and Vertex use different id strings than the Anthropic API. See
`.env.example` for the Vertex variant and the env it needs (`CLOUD_ML_REGION`,
`ANTHROPIC_VERTEX_PROJECT_ID`). Judges are native to MLflow for `anthropic` and
`bedrock`; `vertex_ai:/` judges route through LiteLLM, which the `vertex` extra
pulls in for you.

Outputs land in `eval/results/`:
- `comparison.csv` — per-domain, per-scorer `unwired` / `wired` / `delta`.
- `<domain>__<variant>__rows.csv` — row-level judge scores.
- `raw_metrics.json` — the raw metric rows.
- Traces + `eval_results_table` per run in the MLflow UI.

---

## Reading the result

- The headline is the **`delta(wired-unwired)`** column in `comparison.csv`.
- **Expectation:** positive deltas on `technical-writer` (esp.
  `tw_diataxis_discipline`), smaller positives on `data-engineer` (esp.
  `de_reliability_currency`), ~0 on `slide-designer`. That pattern *confirms the
  wiring is doing what it should*. Uniform deltas everywhere (including the
  control) means the judges are reacting to length/style, not the rubric — tighten
  the judge instructions.
- The smoke test already hinted wired wins but narrowly (41 vs 40 on writing);
  this tells you whether that holds across a sample and where it's strongest.

### Known caveats (don't over-read)
- **No tools in the harness.** Agents are called via the bare API (no Figma MCP),
  so `diagramming-guidelines` is exercised only as "describe in prose." A runtime
  note is appended to **both** variants so it can't bias the A/B.
- **Sample is still small** (4–5 tasks/domain). Bump task counts in `tasks.py` for
  tighter confidence intervals.
- **Judge variance.** Single judge model per criterion. For rigor, run twice with
  different `EVAL_JUDGE_MODEL`s and check the deltas are stable.
- The data-engineer smoke test earlier had a body-trim fairness bug; this harness
  avoids it — `unwired` is the *real* `agent.body`, no hand-editing.

---

## Results checklist

Tick these off as you run and record the mean `delta(wired−unwired)` (1–5 scale).
Mirrors the checklist in the PR description — keep them in sync.

**Run**
- [ ] Prereqs set: `ANTHROPIC_API_KEY`, MLflow ≥ 3.8, `MLFLOW_TRACKING_URI`; `EVAL_AGENT_MODEL` / `EVAL_JUDGE_MODEL` ids verified callable
- [ ] Smoke test green: `run_eval.py --domains technical-writer --limit 1`
- [ ] Full A/B completed: 3 domains × {wired, unwired}
- [ ] `eval/results/comparison.csv` + per-row tables generated

**Findings**
- [ ] **technical-writer** — wired ≥ unwired, largest on `tw_diataxis_discipline`. delta: `___`
- [ ] **data-engineer** — wired ≥ unwired, notably on `de_reliability_currency`. delta: `___`
- [ ] **slide-designer (control)** — `|delta| ≈ 0`. If large, judges are scoring style/length, not the rubric → tighten judge instructions. delta: `___`

**Robustness**
- [ ] Re-ran with a second `EVAL_JUDGE_MODEL`; delta signs stable
- [ ] Task count adequate (bumped `tasks.py` if per-scorer spread too wide)
- [ ] Agent model reflects real use (re-ran with `--agent-model claude-opus-4-8` if needed)

**Decision**
- [ ] Verdict recorded: keep wiring as-is / tune rubrics / revert
- [ ] `comparison.csv` summary pasted as a PR comment

## Files

| File | Purpose |
|---|---|
| `agents.py` | builds wired/unwired system prompts from registry source; traced Anthropic predict_fn |
| `tasks.py` | tasks per domain (the gradient) |
| `scorers.py` | `make_judge` rubric judges + `register_all()` |
| `run_eval.py` | orchestrates evaluate(wired) vs evaluate(unwired) per domain; writes `results/` |
| `pyproject.toml` | standalone uv project (mlflow, anthropic, pandas) |
| `.env.example` | required env vars |

To extend: add tasks in `tasks.py`, tweak judge instructions in `scorers.py`, or
add a domain (also add its agent to `AGENT_FOR_DOMAIN`). The
agent-evaluation skill on this machine can drive deeper analysis of the traces.
