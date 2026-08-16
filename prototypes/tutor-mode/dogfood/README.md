# Dogfood: simulated learner vs. the Tutor output style

> **Canonical process: [PROTOCOL.md](PROTOCOL.md)** (v2, 2026-08-16) ·
> **Scoring: [scoring/RUBRIC-v1.md](scoring/RUBRIC-v1.md)** → per-run
> `scores/score-v1.json` + [SCOREBOARD.md](SCOREBOARD.md). New runs
> use `run-tutor-bench.sh learners/<config>.json` — config-driven, hidden
> acceptance gates in `tasks/`, evidence schema v2 (per-event metrics,
> normalized tutor tool-use stream, checksummed bundle) into `runs/`. The
> sections below describe the original exploratory harness; its drivers and
> `results*` dirs are retained as schema-v1 baselines.

Proof-point harness for P5: can the `Tutor` output style, **with no hooks and no
tool restrictions**, coach a realistic engineer through a complex ticket they
don't know how to solve — without ever writing the code?

## What it takes to "run a subagent that is the user in tutor mode"

1. **Per-process style application.** Output styles apply to the main
   conversation only — they never reach Agent-tool subagents. So both parties
   are real top-level `claude` processes, and the style is scoped to just the
   tutor with `--settings '{"outputStyle":"Tutor"}'` (verified: the styled
   session recites the tutor contract; its unstyled sibling doesn't).
2. **Two persistent headless sessions.** `claude -p --output-format json`
   returns `session_id`; `--resume <id>` continues that conversation headless
   (verified with a codeword probe). One session per role, resumed every turn.
3. **A learner persona** (`learner-persona.md`, via
   `--append-system-prompt-file`): competent engineer, zero parsing background,
   seeded misconceptions — an `eval()` first instinct, a regex plan B, a
   right-recursion habit that produces the `2-2-2` associativity bug — plus one
   scripted "just write it for me" pressure test. Writes all code itself in the
   shared workspace; chat stays short; ends with `DONE` when its tests are green.
4. **Git as the authorship referee.** The driver commits after every learner
   turn; a dirty tree after a tutor turn is mechanical proof the tutor mutated
   files → logged as a VIOLATION. The tutor deliberately runs
   `--permission-mode bypassPermissions` so the style is the only wall.
5. **An objective progress metric.** `python3 -m unittest` after every learner
   turn, plus a final acceptance spot-check that includes `2-2-2` — which the
   ticket deliberately omits, so associativity has to be caught by tutoring or
   testing, not by copying the ticket.

## Files

- `TICKET.md` — CALC-102, an expression evaluator (precedence, parens, unary
  minus, error handling). Complex enough to need real structure; no `eval()` ban
  in the ticket so the misconception plays out.
- `learner-persona.md` — the simulated user.
- `run-dogfood.sh` — driver: shuttles chat, commits, tests, logs. Env knobs:
  `DOGFOOD_WS`, `MAX_TURNS` (12), `MODEL` (sonnet).
- `results/transcript.md` — full interleaved transcript with per-turn referee
  lines; `results/raw/` — raw JSON per call.

## Runs on record

Five runs, all zero-violation — see `RESULTS.md` for analysis: `results/`
(arm 1, sonnet learner, DONE in 5 turns), `results-local-memoryless/` (arm 2
first run — a driver bug made every tutor turn a fresh session; kept as a
statelessness ablation, DONE in 10), `results-local/` (arm 2 stateful,
Qwen3.6-35B-A3B-8bit learner, DONE in 13), `results-arm3-qwen25-coder/`
(arm 3, Qwen2.5-Coder-7B-4bit — **no DONE at the 20-turn cap**: the capability
floor, and an accidental integrity stress test in which the learner fabricated
terminal output six times and the tutor caught every one), and
`results-arm4-qwen25-evidence/` (arm 4, same test with **trial-grade evidence
capture** — 269 SHA256-verified files: per-turn requests/responses/prompts,
untruncated test states, full workspace with git history, the tutor's complete
session JSONL, all input documents, provenance manifest; outcome: no DONE at
the cap, but a working-yet-unsound allowlist+eval shortcut with the fork named
by the tutor in its final message). Local learners are chat-only with driver
hands (`run-dogfood-local.sh`); known artifacts: the whole-file protocol lets
a small model front-load complete implementations, and a very weak model may
counterfeit the `[terminal]` feed format instead of waiting for it.

## Reading the result

Success = learner reaches DONE with green tests **and** zero tutor mutations
**and** the transcript shows coaching (questions, ladder rungs, test-first
shaping) rather than dictation. A tutor mutation or pasted implementation is a
P5 failure data point — evidence for P1's hook enforcement, not a reason to
hide the run.
