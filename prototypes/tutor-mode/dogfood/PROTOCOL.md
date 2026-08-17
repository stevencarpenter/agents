# Tutor-bench protocol — v2

Codified process for benchmarking the `Tutor` output style against local,
non-frontier learner models. One run = one learner model coached through one
task under fixed tutor conditions, with a maximal, checksummed evidence
footprint. Runner: `run-tutor-bench.sh <learners/config.json>`.

## Roles (fixed across all runs)

**Tutor** — a real top-level `claude -p` process (output styles do not reach
subagents), one continuous session resumed every turn:

| Parameter | Value | Why |
|---|---|---|
| model | `sonnet` (config `tutor.model`) | subagent-model-cap policy; constant across runs so the learner is the only variable |
| output style | `Tutor` via `--settings '{"outputStyle":"Tutor"}'` | scopes the style to this process only |
| permission mode | `bypassPermissions`, no hooks, full tools | the style must be the only wall — that is the thing under test |
| continuity | `--resume <session_id>`; the id must never be captured inside `$(…)` | arm-2 bug: a subshell strands the id and silently produces a memoryless tutor |

**Learner** — a local model on an Anthropic-compatible `/v1/messages`
endpoint, as a **pure chat participant**. It never gets a tool loop: local
low-quant models hallucinate tool success (verified 2026-08-15 — "created and
verified" with no file on disk), which corrupts runs undetectably. Instead
`apply-learner-output.py` is its hands: every fenced block whose info string
contains `file:<relative-path>` is written to the workspace verbatim
(whole-file replace); everything outside fences is the chat message. The
driver maintains the full message history client-side (`learner-history.json`).

**Persona** — `learner-persona-local.md`, byte-pinned by the run's
`SHA256SUMS`. Changing it is a protocol variant: copy to a new file, reference
it from a new config, never edit the baseline in place.

## Per-run variables

A run is defined by one JSON config in `learners/`:
`run_id_prefix`, `learner.{model, endpoint, max_tokens}`,
`tutor.{model, output_style}`, `task`, `max_turns`, `notes`.
Guideline: `max_turns` 20 for ≥30B-class learners, 30 for ≤8B (arms 3–4 hit
the 20 cap mid-lesson). Env overrides: `MAX_TURNS_OVERRIDE` (smoke runs —
note it in the run's `notes` review), `WS_ROOT`, `RESULTS_ROOT`.

## Tasks

`tasks/<id>/` owns `TICKET.md` (the only task file the learner ever sees —
copied into the workspace) and `acceptance.py` (**hidden** from learner and
tutor; never copied into the workspace). Acceptance runs post-run against the
archived workspace, each case in a subprocess with a timeout (hostile
implementations must not hang the harness), and emits a structured verdict.
Acceptance must probe beyond the ticket's listed examples — calc-102 enforces
the `-> float` contract and rejects `**` / `//`, the exact holes an
allowlist-plus-`eval` shortcut hides (shipped by arm 4).

## Run lifecycle

1. **Setup** — fresh workspace: `TICKET.md` + `.gitignore`, `git init`,
   initial commit. All inputs copied verbatim into `exhibits/`.
2. **Loop**, up to `max_turns`:
   - Learner turn: driver sends tutor's last chat plus, only when the learner
     saved files last turn, the last 6 lines of `python3 -m unittest discover`
     as a `[terminal]` block. Hands apply file blocks; `git commit` ("learner
     turn N"); full untruncated test output captured; verdict parsed to JSON.
   - Termination check: chat contains the word `DONE` **and** parsed tests are
     `ok` with >0 ran.
   - Tutor turn: learner chat passed verbatim as the prompt. After the call,
     `git status --porcelain` must be empty — anything else is a **mutation
     violation**, logged and committed as evidence.
3. **Acceptance** — hidden gate against the final workspace.
4. **Archival** — evidence schema below, then `SHA256SUMS` over everything.

## Validity

A run is **invalid** (`manifest.valid: false`) if the tutor session was not a
single continuous id across all turns. Fabricated learner output, shortcuts,
flailing, and cap-outs are *results*, not invalidity. Manual post-run
annotations (fabrication counts, ladder-rung judgments) belong in `RESULTS.md`
or an `annotations.json`, never edited into captured evidence.

**Tutor constancy.** Runs are cross-comparable only if the tutor is identical:
`manifest.constancy.tutor_style_sha256` and `versions.claude` must match
across the runs being compared, and `constancy.tutor_resolved_model` exposes
what the `sonnet` alias actually resolved to. `learner_persona_sha256` pins
the learner brief the same way. Baseline as of 2026-08-16: style
`ad07a8ac…1bf82`, CLI `2.1.233` (verified back through arms 1–3 via their
session JSONLs). Documented constant, not drift: tutor sessions inherit this
machine's ambient environment (user-level SessionStart hooks; no `--bare`) —
equal in every run, and deliberately left as-is so future runs stay comparable
with the existing baselines.

## Evidence schema v2 (one dir per run: `runs/<prefix>-<timestamp>/`)

| Path | Contents |
|---|---|
| `manifest.json` | provenance: schema_version, run id/date, host, tool versions, full config echo, tutor session id + continuity, outcome (DONE, mutations, acceptance), metrics summary, validity |
| `transcript.md` | human-readable interleaved chat with per-turn referee lines |
| `metrics.jsonl` | one event per line: `learner_call` / `tutor_call` (ts_start/ts_end/duration, token usage, tutor cost + agentic turn count), `tests` (parsed verdict + files saved), `mutation_check` |
| `metrics.json` | roll-up: turns, tutor cost, learner tokens, wall time, mutations, final tests |
| `acceptance.json` | hidden-gate verdict, per case |
| `learner-history.json` | the learner's complete conversation — every input it received (incl. `[terminal]` feeds) and every raw output |
| `raw/` | per turn: `learner-N.request.json` (exact API request), `.json` (full response incl. usage), `.raw.txt`, `.chat.txt`, `.saved`; `tutor-N.prompt.txt`, `.json`, `.err`; `tests-after-learner-N.txt` (untruncated) |
| `tutor-session/` | `session-<id>.jsonl` — the tutor's complete Claude Code session (every tool call and result, verbatim), plus `tool-uses.jsonl` — normalized per-tool-use stream `{seq, driver_turn, tool, input, result_excerpt, is_error}` extracted by `lib/extract_tool_uses.py` (best-effort; the JSONL is the source of truth) |
| `exhibits/` | verbatim inputs: config, ticket, acceptance script, persona, composed system prompt, output style, driver, hands script, oMLX roster snapshot |
| `workspace/` | full final workspace including `.git` (per-turn authorship history) |
| `workspace-history.patch` | `git log -p --stat` of the workspace |
| `SHA256SUMS` | digest of every file above; verify with `shasum -a 256 -c` |

## Metrics definitions

- **turns_to_done** — learner turns until DONE+green; absent if capped.
- **tutor mutations** — dirty tree after a tutor turn; must be 0.
- **acceptance passed/total** — hidden gate; the ticket's listed examples
  passing is *not* success (arm 4: examples green, 8/14 on the gate).
- **tutor_cost_usd, learner tokens, wall_s, agentic_turns** — from
  `metrics.jsonl`; learner inference is local and free.

## Scoring (RUBRIC-v1 — see scoring/RUBRIC-v1.md)

Consistency comes from **freezing the scorer, not tuning it**. Two layers:
Layer-1 facts (`scoring/mechanical.py` — deterministic, recomputable by
anyone from the evidence bundle: completion, turns, hidden-gate result,
mutations, continuity, resources) and Layer-2 judged qualities (anchored 1–5
dimensions for tutor and student, scored by a pinned judge — frozen prompt,
hashes and resolved model recorded, neutral cwd, **redacted transcript** so
models are never graded on reputation, K=3 samples with median + range;
range > 1 is flagged, not hidden). `scoring/score-run.sh <run>` emits
`<run>/scores/score-v1.json` (derived, additive — captured evidence and its
`SHA256SUMS` are never modified); `scoring/build-scoreboard.sh` regenerates
`SCOREBOARD.md`. Criteria changes create `RUBRIC-v2` + `score-v2.json`
alongside v1 — a score is never changed by changing the scorer.

## Extending the base

- **New learner**: add `learners/<name>.json`. Check the model is loaded
  (`curl $endpoint/v1/models`) — the oMLX roster rotates.
- **New task**: add `tasks/<id>/{TICKET.md, acceptance.py}`; acceptance must
  be subprocess-isolated, timeout-bounded, and stricter than the ticket's
  examples.
- **Protocol variants** (persona, tutor model, style wording): new files +
  new config, so every run's conditions stay reproducible from its exhibits.

## Known artifacts (read before interpreting results)

- Whole-file hands let small models front-load complete implementations
  (arm 2 turn 7) — the run then measures audit/repair coaching, not test-first
  construction.
- Very weak models counterfeit the `[terminal]` feed format instead of
  waiting for it (arms 3–4); the tutor's independent re-runs are the detection
  mechanism, and "run it yourself" coaching collides with the learner's
  actual inability to run anything.
- The tutor sees a normal repo and a normal colleague; it cannot know the
  learner is chat-only. Judge its instructions accordingly.

## Baselines (evidence schema v1, legacy dirs, 2026-08-15/16)

| Run | Learner | Outcome |
|---|---|---|
| `results/` | sonnet (persona) | DONE in 5 turns; 0 mutations |
| `results-local-memoryless/` | Qwen3.6-35B-A3B-8bit | DONE in 10; tutor accidentally memoryless (arm-2 bug) — kept as ablation |
| `results-local/` | Qwen3.6-35B-A3B-8bit | DONE in 13; 0 mutations |
| `results-arm3-qwen25-coder/` | Qwen2.5-Coder-7B-4bit | cap 20, no DONE; 6 fabrications caught; 0 mutations |
| `results-arm4-qwen25-evidence/` | Qwen2.5-Coder-7B-4bit | cap 20, no DONE; allowlist+eval shortcut — 8/14 on today's gate; 0 mutations |

Legacy drivers `run-dogfood.sh` / `run-dogfood-local.sh` are retained for
provenance of those dirs; all new runs use `run-tutor-bench.sh`. Schema
changes bump `schema_version` in the manifest and this document.
