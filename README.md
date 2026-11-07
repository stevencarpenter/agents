# agents

Canonical registry for non-sensitive AI agent definitions and reusable language rubrics.

This public snapshot contains general-purpose agents, reusable skills, registry tooling,
and synthetic evaluation fixtures. Employer-specific agents, business context, private
infrastructure details, and credentials are intentionally excluded.

The source format for agents is Claude-native subagent Markdown: YAML frontmatter plus a body in `agents/<name>/agent.md`. Claude can consume this shape directly. Codex emission is intentionally tiny and conservative until the user-agent load path is verified.

Shared reusable guidance lives under `skills/<name>/SKILL.md`. Language expert agents should refer to a shared skill/rubric instead of duplicating the whole checklist in every prompt.

Sensitive work-domain agents do not belong in this repository. Store them in their
owner's private configuration outside this public registry.

## License

MIT. See [LICENSE](LICENSE).

## Language Expert Pattern

Language expert agents should be narrow and router-friendly:

- `<language>-idiom-reviewer`
- `<language>-implementer`
- `<language>-api-designer`
- runtime or concurrency specialists where the language warrants them
- safety, interop, migration, or performance specialists where the risk justifies a separate context window

Rust has `rust-*`: idiom-reviewer, implementer, api-designer, async-concurrency-reviewer,
unsafe-ffi-auditor, performance-profiler, test-strategist, toolchain-auditor.

All Rust agents share `skills/rust-guidelines/SKILL.md`, which summarizes and links to the Rust API Guidelines, Microsoft Pragmatic Rust Guidelines, and async Rust references.

C++, C, Lua, and Unreal Engine 5.8 follow the same pattern at the same depth, each with a
shared `<language>-guidelines` skill that carries an eval suite:

- `cpp-*`: implementer, idiom-reviewer, api-designer, memory-safety-auditor, concurrency-reviewer, performance-profiler, test-strategist, build-auditor
- `c-*`: implementer, idiom-reviewer, abi-designer, memory-safety-auditor, performance-profiler, test-strategist, build-auditor
- `lua-*`: implementer, idiom-reviewer, api-designer, embedding-auditor, performance-profiler, test-strategist
- `unreal-*`: implementer, reviewer, gameplay-architect, render-specialist, physics-specialist, editor-automation, performance-profiler, build-auditor (these also inline `cpp-guidelines`)

## Reverse-engineering pattern

Agents that work from a shipped binary share two rubrics: `reverse-engineering-guidelines`
(the REA playbook: provider setup, session discipline, string-to-code, offset mapping,
verification pass, findings file contract) and `re-provenance-guidelines` (the label vocabulary
Observed, Verified, Inferred, Derived, Tunable, Design, Spec; precedence; porting rules;
fidelity tiers). The agents are `game-data-format-analyst` (shipped data first),
`rea-binary-analyst` (REA sessions and findings), `re-findings-auditor` (provenance review),
`re-findings-porter` (vendoring and wiring into a consumer repo), `physics-model-reconstructor`
(simulation model and reference oracle), and `graphics-pipeline-reconstructor` (render passes
and encodings). `tools/hooks/re-workspace-context.sh` is a SessionStart hook that prints the
label and precedence reminder inside such workspaces. Findings packages and game data never
live in this repository.

Product-focused agents should compose language expertise with repo-specific context: layout, domain language, exact gates, CI/deploy quirks, and known failure modes. Do not bake product secrets into public language agents.

## Mechanical leaf agents

Pure retrieval/pass-through agents (`Explore` and the read-only ops agents) are marked `x-mechanical: true`: they skip the universal `tool-priority` inline and carry a terse output contract to minimize per-call tokens. See [docs/mechanical-agents.md](docs/mechanical-agents.md) for the rationale and how the carve-out is enforced.

## Commands

### Enforced local-read-only agents

Agents requiring tool isolation must declare all of these fields:

```yaml
x-registry-permission: read-only
x-isolated-read-only: true
x-allow-tools-allowlist: true
tools: Read, Glob, Grep
disallowedTools: Write, Edit, MultiEdit, NotebookEdit, Bash, Agent, Task
```

The validator permits only a nonempty subset of `Read`, `Glob`, and `Grep`.
Claude exports use its native tool allowlist. OpenCode exports deny all tools
except the named local readers. Shell, browser, MCP, delegation, and dynamic
tool discovery are not granted. These agents cannot retrieve live API data.
Supply exported evidence instead. A skill or prompt alone does not enforce this.

Codex, Cursor, and Copilot exports are refused because these emitters cannot
preserve that tool boundary. Mixed-target installation fails before writing
anything. Ordinary `read-only` agents retain their existing permissions and
are not equivalent to isolated agents.

Host configuration, hooks, plugins, or a separate unrestricted parent session
are outside this boundary; use a trusted host configuration and do not ask a
parent agent to execute the recommendations.

The emitted policy follows [Claude tool restrictions](https://code.claude.com/docs/en/sub-agents#available-tools)
and [OpenCode permission matching](https://opencode.ai/docs/permissions/).

### Validation and emission

```sh
uv run python -m unittest discover -s tests
uv run python -m agent_registry.cli validate
uv run python -m agent_registry.cli emit-codex
```

or:

```sh
just check
```

## Layout

```text
agents/<name>/agent.md       # one agent per directory
skills/<name>/SKILL.md       # shared rubrics; optional evals/, scripts/, bench/
schema/                      # agent and skill frontmatter schemas
agent_registry/              # validation plus one emitter per target
tools/routing/, tools/hooks/ # session-start routing block and hook scripts
tests/                       # registry, routing, and challenge fixtures
eval/                        # MLflow A/B of skill inlining
mining/                      # hippo.db queries
docs/                        # decision records and specs
```
