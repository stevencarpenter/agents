# Hippo as the store for agent evaluation data

Epic plan, 2026-10-24. Tickets live on the Kaneo `HIPO` board under epic HIPO-57.
The work touches three repos: `hippo` (capture, schema, queries), `agents` (blind-review
emitters and benchmark), and `dotfiles` (deployment). Each ticket names its repo.

## Goal

Two questions about every agent in this registry need data that persists across sessions:

1. **Score:** how does the agent perform on benchmark tasks with known answers? Today
   `skills/blind-review/bench/results.jsonl` answers this for the mechanical reviewer only.
2. **Effectiveness:** on real work, did the agent help ship better, more reliable, more idiomatic
   code? Today `skills/blind-review/scripts/review_log.py` keeps a local ledger, with no link to
   what happened after the review.

Hippo already captures every agent session on this machine. The epic makes hippo the system of
record for both questions: capture the evaluation facts that sessions already contain, accept
explicit evaluation records (findings, verdicts, escaped defects, benchmark runs), link them to
later commits, and expose per-agent scorecards.

## Review findings

The review on 2026-10-24 was read-only. Row counts are from the live database on that date.

### Deployment

- Twelve `com.hippo.*` launchd jobs run the daemon, the brain, the Claude session watcher (FSEvents
  on `~/.claude/projects/**/*.jsonl`), pollers for Codex, Cursor, Pi, and opencode, the GitHub CI
  poller, the watchdog, a probe, the metrics exporter, and an inference-server guard.
- The daemon binary is a symlink to a release build in the hippo checkout. The brain service runs
  from an installed copy in `~/.local/share/hippo-brain`. The MCP server runs from the checkout
  (`uv run --project <checkout>/brain hippo-mcp`). dfm manages the hippo config directory, the
  zsh hook sourcing, the SessionStart handler, and the MCP registration; it does not manage the
  binaries, the launchd plists, or the brain copy.
- The SessionStart hook is a no-op since 2026-04-25. Capture runs only through the watchers.
- `hippo doctor` passes with warnings. The daemon log shows 58 `failed to insert session segments
  after SQLITE_BUSY retry` errors on one day, and the watchdog raises "source silent" alarms for
  Claude capture several times a day. The causal link is inferred, not verified.
- The MCP server is registered for Claude Code, Cursor, and opencode. It is not registered for
  Codex, although the usage-measurement doc assumes it is.

### Captured data

- The database is 914 MB, schema v27. Main tables: `agentic_sessions` 23,239 rows (claude-code
  17,019; codex 3,277; pi 1,870; cursor 673; opencode 402), `events` 87,126 (53,886 synthetic
  probes), `knowledge_nodes` 35,758, `entities` 78,973, CI `workflow_runs` 8,802, `lessons` 32.
- Per Claude segment: prompts (500 chars each), assistant text (300 chars), tool calls as
  `{name, summary}`, a summed `token_count`, git branch, cwd, `is_subagent`, and
  `parent_session_id`. 4,282 claude-code rows are subagent transcripts.
- Redaction runs at write time and is regex-based. Enrichment runs on a local model. The only
  confirmed outbound flow is optional classification of node summaries.
- There is no automatic deletion. Event payload expiry exists but runs only on demand.

### Fields hippo drops that evaluation needs

All of these exist in the Claude Code transcripts that hippo already reads.

| Field | Source record | Hippo today |
|---|---|---|
| Subagent type (`agentType`), `spawnDepth`, `toolUseId`, `finished` | `subagents/agent-<id>.meta.json` | not read; `agent` column empty on every claude-code row |
| Model ID, requested model, effort | `assistant.message.model`, `requestedModel`, `effort` | `model` empty on every claude-code row |
| Cache tokens, service tier | `assistant.message.usage` | only input + output summed; input may be read from the wrong record |
| Total cost, duration, lines added and removed | `cost-state` | not read |
| PR number, repo, URL | `pr-link` | not read |
| Session title | `ai-title` | `title` empty |
| Hook outcomes, permission decisions | `system` `stop_hook_summary`, `user.permissionDecision` | not read |
| Agent tool call `subagent_type` | `Agent` tool input | only `description`, cut to 100 chars |

Codex and Cursor rows carry no model and no token counts. opencode is the only harness with
`agent`, `model`, snapshot diffs, and commit messages.

### Query surfaces

- MCP: 12 read-only tools (`search_hybrid`, `agent_query`, `get_lessons`, `get_ci_status`, and
  others). None returns per-agent aggregates.
- Brain HTTP API and CLI cover the same reads. Raw columns are reachable only through read-only
  SQL.
- Existing measurement: the hippo usage metric (hippo calls per 1,000 tool calls), `hippo-bench`
  (enrichment models, not agents), `hippo-eval` (retrieval quality), and the `agent_benefit`
  study (does hippo help agents; epic HIPO-49).
- Lessons come only from CI annotations and capture alarms. No lesson type covers review outcomes.

### What hippo can answer today

| Question | Today | Missing |
|---|---|---|
| How often was each subagent type invoked, where, at what cost? | Partly: subagent rows exist | agent type, model, full tokens, cost |
| Was a flagged line changed later, and in which commit? | No | finding records, commit linkage |
| Which findings did the user accept or reject? | No | verdict records |
| Did a later fix trace back to code an agent reviewed? | No | escape records, linkage |
| How did benchmark scores change over time and per model? | No (JSONL in the agents repo) | benchmark run records |

## Design

### Principles

- **Write-time records over inference.** A 2026-06-21 attempt to score subagents only from old
  transcripts concluded that outcomes cannot be recovered after the fact. Outcomes (verdicts,
  escapes, benchmark scores) are recorded when they happen, by the tool that knows them.
- **Capture what transcripts already hold.** Agent type, model, tokens, cost, and PR links need no
  new instrumentation, only parsing.
- **One explicit ingest path.** Evaluation records enter through one typed command,
  `hippo ingest agent-eval <file.jsonl>`, validated against a versioned schema. No free-form
  event type.
- **Private stays local.** Findings hold code lines and private paths. They go through the
  redaction engine, are excluded from derived indexes and from outbound classification (same
  rule as HIPO-7), and never leave the machine. The public `agents` repo keeps only synthetic
  benchmark data.
- **The verdict is append-only**, like HIPO-9's `retrieval_events`: the latest verdict wins, and
  automatic verdicts carry `auto = true`.

### Data model (proposed; settled by the design ticket)

- `agentic_sessions`: fill the existing `agent` and `model` columns; add `effort`,
  `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `spawn_depth`,
  `parent_tool_use_id`.
- `agentic_session_facts` (one row per session): `cost_usd`, `duration_ms`, `lines_added`,
  `lines_removed`, `pr_number`, `pr_repo`, `title`.
- `eval_review_runs`: run ID, agent, mode (for example `mechanical`), model ID, CLI version,
  repo, base, input hash, started and finished times.
- `eval_findings`: finding ID, run ID, repo, path, side, line, line text (redacted), severity,
  confidence, category, claim.
- `eval_verdicts` (append-only): finding ID, verdict (`accepted`, `false-positive`, `not-useful`,
  `duplicate`, `likely-addressed`), commit, note, `auto`, time.
- `eval_escapes`: repo, path, line, commit that fixed it, note, time.
- `eval_bench_runs`: the `bench.py` record (scores, per-case hits, cases hash, brief hash,
  commit, model IDs).

### Data flow

1. The watchers parse the new transcript fields and `meta.json` files (Phase 1).
2. `review_log.py` and `bench.py` write JSONL records and call `hippo ingest agent-eval` when
   hippo is installed. The local JSONL stays as the fallback and the audit trail (Phase 2).
3. A brain job links open findings to later commits in the same repo and writes `auto` verdicts
   with the commit SHA (Phase 2).
4. `get_agent_scorecard` (MCP) and `hippo agents report` (CLI) aggregate per agent, model, and
   project (Phase 3).
5. Accepted findings and escapes on real code become a private, local benchmark corpus, which
   removes the current ceiling effect (Phase 3).

## Phases and tickets

Gates: hippo `mise run test`; agents `just check`;
dotfiles CI hygiene checks.

| Phase | ID | Ticket | Repo | Priority |
|---|---|---|---|---|
| 0 | HIPO-58 | Stop SQLITE_BUSY drops in Claude session ingest | hippo | high |
| 1 | HIPO-59 | Record subagent type from `meta.json` | hippo | high |
| 1 | HIPO-60 | Record model, effort, and full token usage per Claude segment | hippo | high |
| 1 | HIPO-61 | Ingest `cost-state`, `pr-link`, and `ai-title` records | hippo | medium |
| 1 | HIPO-62 | Record hook outcomes and permission decisions | hippo | low |
| 2 | HIPO-63 | Design the agent-eval schema and ingest contract (decision gate) | hippo | high |
| 2 | HIPO-64 | Implement `hippo ingest agent-eval` and the schema migration | hippo | medium |
| 2 | HIPO-65 | Emit blind-review findings, verdicts, escapes, and bench runs to hippo | agents | medium |
| 2 | HIPO-66 | Link findings to later commits as automatic verdicts | hippo | medium |
| 3 | HIPO-67 | Add per-agent scorecards to MCP and the CLI | hippo | medium |
| 3 | HIPO-68 | Build a private benchmark corpus from accepted findings and escapes | agents, hippo | medium |
| 4 | HIPO-69 | Run the MCP server from the installed brain, not the checkout | hippo, dotfiles | medium |
| 4 | HIPO-70 | Register the hippo MCP server for Codex | dotfiles | low |

The board relations are the source of truth for order. Phase 0 runs first because dropped segments corrupt every count below it. Phase 1 tickets
are independent of each other. In Phase 2, the design ticket blocks the ingest ticket, which
blocks the emitter and the linkage tickets. Phase 3 needs Phases 1 and 2. Phase 4 can run at any
time.

## Risks

- **Privacy:** findings and escapes hold private code. Mitigation: redaction, exclusion from
  derived indexes and outbound flows, local-only storage, and a canary test like HIPO-8.
- **Write contention:** new writers add SQLite load during the period when `SQLITE_BUSY` drops
  already occur. Mitigation: Phase 0 first; ingest in short transactions.
- **Transcript retention:** Claude Code deletes old transcripts, so `meta.json` backfill covers
  only files still on disk. Record the backfill coverage instead of claiming full history.
- **Schema churn:** Claude Code record formats change between versions. Mitigation: parse
  defensively, record the CLI `version` field per segment, and test against fixture transcripts.

## Related tickets

- HIPO-49 (agent-benefit evaluation): scorecards give that study real usage data.
- HIPO-9 (`retrieval_events`): the same append-only feedback pattern.
- HIPO-7 (credential spans in derived indexes) and HIPO-13 (payload expiry): rules that findings
  must follow.
- HIPO-18 (Kaneo sync): a ticket closed for a finding is a possible verdict signal.

## Deployment findings outside this epic

The review also found these. They are not filed under this epic:

- No scheduled backup exists; about 3 to 4 GB of manual snapshots are never pruned.
- The `otel/` data (1 GB) has no visible retention.
- One watched CI repo returns 404 on every poll, so the CI poller exits 1.
- The running daemon is three commits behind the checkout.
- Short-lived jobs log OpenTelemetry meter shutdown errors on every run.
- The hippo usage-metric re-measures scheduled for 2026-08-30 and 2026-09-23 have no snapshots.
- Synthetic probe rows are 62% of `events` and 99% of `browser_events`, with no known prune.
