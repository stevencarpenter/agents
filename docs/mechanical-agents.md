# Mechanical leaf agents (`x-mechanical`)

A design record for the token-minimization carve-out applied to pure
retrieval/pass-through agents.

## Problem

Some agents in this registry are **mechanical leaves**: they take an
already-specified request and execute it with no synthesis of their own.
`Explore` greps for code; `docs-lookup`, `grafana-read`, `hippo-query`,
`linear-ops`, and `railway-read` run an already-formed query or CRUD against a
single MCP server. The caller has already made every judgment call; the agent
just fetches and reports.

These agents run on `haiku` and are invoked frequently, so every line of their
prompt is paid on every call. Two things were inflating that cost:

1. **A force-inlined rubric they can't use.** Every agent was required to inline
   the shared `tool-priority` skill (~24 lines). That rubric tells an agent to
   prefer IDEA/LSP/codegraph, use `Bash` for gates, and split work across
   sub-teams. But the five ops agents carry a hard `tools:` MCP allowlist that
   **excludes all of those tools** — so the advice is unreachable. On `Explore`
   it is worse than unreachable: the rubric says *"use specialized agents or
   teams,"* which directly contradicts `Explore`'s own brief (*"you are a leaf
   worker: don't spawn further subagents"*).

2. **No output contract.** Nothing capped output length, so a cheap model would
   wrap bare findings in preamble and "what this means" narration.

For `Explore`, the inlined rubric alone was more than half the emitted prompt
(43 lines total, ~17 of them the agent's actual brief).

## Decision

Introduce an explicit frontmatter marker, `x-mechanical: true`, for mechanical
leaf agents. A mechanical agent:

- **Does not inline `tool-priority`.** The rubric is dead weight (unreachable
  under the MCP allowlist) or contradictory (`Explore`), so it is dropped.
- **Ends its brief with a hard output contract** — e.g. `Output: … No preamble`
  — so the model returns a bare data payload, not prose.

### Why a marker, not a predicate

Exempting by inferred properties (e.g. "read-only + allowlisted") is wrong:
several *heavyweight* reviewers are also read-only, so permission alone can't
tell a grep leaf from an architecture auditor. The marker declares intent at the
source and keeps the invariant machine-enforced with a documented carve-out.
Because it names *what the agent is* (mechanical) rather than *what it opts out
of*, it can gate other leaf-appropriate behavior later.

### What is deliberately kept

Minimization stops at the point where cutting text invites expensive mistakes:

- **Escalation guardrails stay.** `grafana-read` still refuses writes,
  `railway-read` still refuses mutations, `linear-ops` still refuses to guess
  IDs. On a cheap model, one bad mutating call or invented query costs far more
  than the tokens those lines occupy.
- **`Explore` keeps one judgment line** — *prefer codegraph/LSP semantic search
  over raw `rg` when the repo is indexed*. That single choice is `Explore`'s only
  real value over the caller running grep directly; minimizing it away would make
  the agent strictly worse than the tool it wraps. The five ops agents are true
  pass-throughs and keep no such line.

## Mechanism

- **Marker:** `x-mechanical: "true"` in agent frontmatter. Documented in
  [`schema/agent.schema.json`](../schema/agent.schema.json).
- **Emit:** the marker is not in the Claude emitter's `_PASSTHROUGH_KEYS`, so it
  never leaks into emitted output; it is a build-time signal only.
- **Enforcement (tests):**
  - `test_mechanical_agents_skip_tool_priority` — a mechanical agent must **not**
    inline `tool-priority`, in source or in the emitted body. This pins the
    carve-out so the rubric can't silently creep back onto a pass-through agent.
  - `test_real_agents_use_tool_priority_and_no_unreviewed_tools_allowlists` and
    `test_real_claude_emits_inherited_tools_shape` — the universal
    `tool-priority` invariant still holds for every **non**-mechanical agent.

## Result

Emitted prompt (what the model receives) per invocation:

| Agent | Before | After |
|---|---|---|
| `Explore` | 43 lines | 17 |
| `docs-lookup` / `grafana-read` / `hippo-query` / `linear-ops` / `railway-read` | brief + ~24-line rubric | 15–17, rubric gone |

Roughly a 60% cut in prompt size on the highest-frequency, lowest-judgment
agents, with zero capability loss on the pure pass-throughs and one judgment
line preserved on `Explore`.
