# Reverse-engineering and game-language agent families: design

Written 2026-11-06. Source: a SnowRunner findings package (HANDOFF, SPEC, AGENTS errata), a
Roadcraft REA workspace (`findings/`, `evidence/`), the Windrow consumer project, and this
registry's Rust family as the depth benchmark. None of those trees live in this repo.

## 1. Intent

The user reverse-engineers games they own with REA to learn how they work, then builds original
systems (Rust simulation, Unreal 5.8 rendering, C ABI glue) from the findings. Two campaigns
exist. Their process knowledge lives in handoff documents and session memory, not in the agent
registry. Coding agents therefore repeat setup mistakes, present game tuning as measurement, and
lose the evidence trail.

This design moves that knowledge into reusable skills and narrow agents, and adds the language
families those consumer projects need: C++, C, Lua, and Unreal Engine 5.8.

## 2. Goals, non-goals, anti-goals

Goals:

1. A coding agent can run an REA campaign on a new binary with the measured playbook (provider
   setup, session discipline, string-to-code, offset mapping, verification pass).
2. A coding agent can port findings into a codebase with provenance labels, errata precedence,
   open items as parameters, and a reference model as a test oracle.
3. C++, C, Lua, and Unreal families match the Rust family: one shared rubric with source of
   truth, core rubric, anti-slop list, verification, adversarial checklist, output contract, and
   an eval suite; plus narrow agents per operating mode.

Non-goals:

- No product-specific agents. Windrow and the two game packages stay in their own repositories.
- No runtime hook that calls REA. Hooks only inject context.
- No vendoring of game data, shaders, or decompiled code into this public registry.

Anti-goals (works but fails the intent):

- A monolithic "reverse engineer" agent with no evidence contract.
- Language rubrics that restate the Rust one with words swapped.
- A port agent that copies decompiled code or shipped shaders instead of describing behaviour.

## 3. Constraints

- Registry format: `agents/<name>/agent.md` frontmatter plus body; `skills/<name>/SKILL.md`.
  Description must contain "Use when". Every non-mechanical agent inlines `tool-priority`.
  Read-only agents declare `disallowedTools: Write, Edit, MultiEdit, NotebookEdit`.
- Skill closure: a skill body that says "apply `X`" forces every agent inlining it to list `X`.
- `just check` must pass (tests, validate, all emitters).
- Public repository: no secrets, no private infrastructure names, no customer data.
- Development platforms are macOS and Linux. Do not favour Windows conventions.

## 4. Decisions

### 4.1 Skills

| Skill | Holds |
|---|---|
| `reverse-engineering-guidelines` | REA workspace layout, provider setup values, session discipline, use and avoid tool table, analysis order (identity, data first, string to code, offset windows, hash-registered fields, vtables, instruction-level verification), findings file contract, package and ledger rules, cost planning |
| `re-provenance-guidelines` | The label vocabulary (Observed, Verified, Inferred, Derived, Tunable, Design, Spec), precedence when sources disagree, porting rules, fidelity tiers and acceptance tests, reference-model registries, citation format, vendoring rules, builder check |
| `cpp-guidelines` | C++20 and later rubric at Rust depth, with evals |
| `c-guidelines` | C17 and C23 rubric at Rust depth, with evals |
| `lua-guidelines` | Lua 5.4 and LuaJIT rubric, embedding and C API, with evals |
| `unreal-guidelines` | Unreal Engine 5.8 rubric: modules, reflection, GC, threading, Chaos, Niagara, Nanite, materials, editor automation, build tooling, with evals |

### 4.2 Reverse-engineering agents

| Agent | Permission | Mode |
|---|---|---|
| `rea-binary-analyst` | edit | Runs REA sessions against a binary, writes findings and evidence, keeps snapshots |
| `game-data-format-analyst` | edit | Data-first pass: containers, tables, scripts, schema from error strings; extraction tools and JSON tables |
| `re-findings-auditor` | read-only | Verifies a findings package: citations resolve, labels consistent, inferences separated, errata applied, no copied code or assets |
| `re-findings-porter` | edit | Ports findings into a consumer codebase with labels, named open items, and vendored citations; routes language work to the language implementers |
| `physics-model-reconstructor` | edit | Builds a simulation model and reference oracle from findings: formulas, constants, units, registries, acceptance tests |
| `graphics-pipeline-reconstructor` | edit | Rebuilds a render technique from findings: passes, encodings, atlases, shader behaviour, in the target engine |

### 4.3 Language agents

C++ (8): `cpp-implementer`, `cpp-idiom-reviewer`, `cpp-api-designer`, `cpp-memory-safety-auditor`,
`cpp-concurrency-reviewer`, `cpp-performance-profiler`, `cpp-test-strategist`, `cpp-build-auditor`.

C (7): `c-implementer`, `c-idiom-reviewer`, `c-abi-designer`, `c-memory-safety-auditor`,
`c-performance-profiler`, `c-test-strategist`, `c-build-auditor`.

Lua (6): `lua-implementer`, `lua-idiom-reviewer`, `lua-api-designer`, `lua-embedding-auditor`,
`lua-performance-profiler`, `lua-test-strategist`.

Unreal (8): `unreal-implementer`, `unreal-reviewer`, `unreal-gameplay-architect`,
`unreal-render-specialist`, `unreal-physics-specialist`, `unreal-editor-automation`,
`unreal-performance-profiler`, `unreal-build-auditor`.

Reviewers and auditors are read-only. Implementers, architects, and specialists that write code
are edit. Each agent lists its family rubric and `tool-priority`. Unreal agents also list
`cpp-guidelines`.

### 4.4 Hook

`tools/hooks/re-workspace-context.sh`: a SessionStart hook. When the working directory holds
`findings/` and `evidence/`, or a `SPEC/README.md` with a label table, it prints the reading
order, the precedence rule, and the label reminder. Wiring into settings stays in dotfiles.

### 4.5 Routing

`tools/routing/routing-overlay.md` gains disambiguation rules: REA family order (data first,
then binary, then auditor, then porter), language family stacking (idiom reviewer first, then
specialists), Unreal C++ routes to the Unreal family, and Windows-only advice is rejected.

## 5. Left to the builder

- Exact wording of each language rubric and its eval fixtures.
- Which Unreal 5.8 feature statuses to cite (take them from the release notes, mark Experimental
  and Beta as such).
- Test names in `tests/test_agent_registry.py` for the new families.
