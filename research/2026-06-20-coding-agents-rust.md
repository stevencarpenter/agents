# Coding Agents And Idiomatic Rust Research Log

Date: 2026-06-20
Timezone: America/Denver
Repo: `agents`

## Original Prompt

```text
Okay, I want you to research how to craft the best coding agents as of today. This field is moving fast, so bias recency (within reason). I really need some expert rust focused agents that will bias towards idiomatic rust. We will have a pattern of language expert agents, so think about us having python, scala, java, kotlin, swift, terraform, and other potential language focused agents. There will also be product focused agents that might be custom, or vendored in. This additional context is just meant to steer your architecture towards the final product, not inhibit the actual ask repeated as follows: Okay, I want you to research how to craft the best coding agents as of today. This field is moving fast, so bias recency (within reason). I really need some expert rust focused agents that will bias towards idiomatic rust.
```

## Research Scope

- Bias recent 2025-2026 agent guidance, but keep stable primary Rust canon where it remains authoritative.
- Focus on coding-agent design, subagents, context/tool boundaries, and how to make Rust agents bias toward idiomatic Rust.
- Treat future language expert agents as a product requirement: Rust now, later Python, Scala, Java, Kotlin, Swift, Terraform, etc.
- Treat product-focused agents as a separate composition layer, not a reason to bake product context into every language expert.

## Source Ledger

### Agent Architecture And Subagent Design

1. Anthropic, "Building Effective AI Agents"
   - URL: https://www.anthropic.com/engineering/building-effective-agents
   - Retrieved: 2026-06-20
   - Finding: Agent systems should start simple, expose planning/transparency, and invest in tool/agent-computer-interface design and testing before adding complex orchestration.
   - Relevance: Supports using narrow single-purpose language agents before building large multi-agent workflows.

2. Anthropic, "Effective context engineering for AI agents"
   - URL: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
   - Retrieved: 2026-06-20
   - Finding: Agent quality depends on curating the whole context state: system instructions, tools, MCP/external data, history, and evolving loop state.
   - Relevance: Supports separating shared language rubrics from product agents so each agent receives only the context it needs.

3. Anthropic, "Writing effective tools for AI agents - with agents"
   - URL: https://www.anthropic.com/engineering/writing-tools-for-agents
   - Retrieved: 2026-06-20
   - Finding: Tool quality matters heavily; choose bounded tools, namespace functionality, return meaningful context, optimize tool output for token efficiency, and test tools with agents.
   - Relevance: Supports narrow tool access per agent and verification commands as first-class agent behavior.

4. Claude Code Docs, "Create custom subagents"
   - URL: https://code.claude.com/docs/en/sub-agents
   - Retrieved: 2026-06-20
   - Finding: Subagents are independent context windows with custom prompts, specific tool access, independent permissions, and description-based delegation.
   - Relevance: Supports canonical agent files with clear "Use when" descriptions and narrow scope.

5. Claude Code Docs, "Claude Code settings"
   - URL: https://code.claude.com/docs/en/settings
   - Retrieved: 2026-06-20
   - Finding: Claude subagents can be user-level under `~/.claude/agents/` or project-level under `.claude/agents/`, as Markdown files with YAML frontmatter.
   - Relevance: Confirms the repo's Claude-native Markdown canonical format remains a good base.

6. Claude Code Docs, "Extend Claude with skills"
   - URL: https://code.claude.com/docs/en/skills
   - Retrieved: 2026-06-20
   - Finding: Skills, subagents, plugins, hooks, memory, and permissions are complementary extension surfaces.
   - Relevance: Supports putting stable reusable Rust rubric material in a skill/rubric layer and using agents for task-specific application.

7. OpenCode Docs, "Agents"
   - URL: https://opencode.ai/docs/agents/
   - Retrieved: 2026-06-20
   - Finding: OpenCode has primary agents and subagents; agents have custom prompts, models, and tool access, and can be invoked manually or automatically.
   - Relevance: Confirms the product direction should preserve the conceptual distinction between primary/build agents, planning/read-only agents, and specialist subagents.

8. OpenCode Docs, "Agent Skills"
   - URL: https://opencode.ai/docs/skills/
   - Retrieved: 2026-06-20
   - Finding: OpenCode supports reusable `SKILL.md` definitions loaded on demand.
   - Relevance: Adds support for a portable language-rubric skill layer, even though current implementation should not target OpenCode artifacts yet.

9. Claude Code Docs, "Common workflows"
   - URL: https://docs.anthropic.com/en/docs/claude-code/common-workflows
   - Retrieved: 2026-06-20
   - Finding: Delegating research to subagents preserves main context when exploration would flood the conversation.
   - Relevance: Supports a read-only `rust-idiom-reviewer` and separate implementer instead of one agent doing everything.

10. Business Insider, "Forget prompt engineering: 'Loop engineering' is all the rage now"
    - URL: https://www.businessinsider.com/what-are-loops-ai-engineering-tips-2026-6
    - Retrieved: 2026-06-20
    - Finding: Recent industry language is shifting toward loops/agent workflows with automation, worktrees, skills, plugins/connectors, and subagents; token cost and careful loop design matter.
    - Relevance: Secondary source only; useful trend signal, not a design authority.

11. GitHub Community Discussion, "Best practices for using GitHub AI coding agents in production workflows?"
    - URL: https://github.com/orgs/community/discussions/182197
    - Retrieved: 2026-06-20
    - Finding: Treat AI coding agents like fast junior engineers: clear problem statements, rationale, assumptions, draft PRs, human review, and protected branches.
    - Relevance: Supports evidence-first output contracts and not letting agents own final correctness.

### Rust Canon And Rust-for-Agents Sources

12. Rust API Guidelines, "Checklist"
    - URL: https://rust-lang.github.io/api-guidelines/checklist.html
    - Retrieved: 2026-06-20
    - Finding: Official Rust API guidance emphasizes type safety, newtypes, meaningful argument types, bitflags for flags, builders for complex construction, validation, debugability, and future-proofing.
    - Relevance: Core source for the Rust idiom rubric.

13. Microsoft, "Pragmatic Rust Guidelines"
    - URL: https://microsoft.github.io/rust-guidelines/
    - Retrieved: 2026-06-20
    - Generated: 2025-11-05
    - Finding: Pragmatic design guidelines for idiomatic Rust at scale, built on the Rust API Guidelines and shaped around safety, cost of goods/performance, and maintainability.
    - Relevance: High-value modern Rust guidance, especially because it explicitly considers AI agents.

14. Microsoft, "Pragmatic Rust Guidelines - Checklist"
    - URL: https://microsoft.github.io/rust-guidelines/guidelines/checklist/index.html
    - Retrieved: 2026-06-20
    - Finding: Condensed checklist includes static verification, `#[expect]` for lint overrides, public `Debug`, avoiding weasel names, structured logging, strong types, additive features, unsafe discipline, hot-path profiling, yield points, and canonical docs.
    - Relevance: Good source for concrete agent-review checklist items.

15. Microsoft, "Pragmatic Rust Guidelines - AI Guidelines"
    - URL: https://microsoft.github.io/rust-guidelines/guidelines/ai/index.html
    - Retrieved: 2026-06-20
    - Finding: APIs easier for humans are easier for AI; Rust's compiler helps agents; AI-effective Rust needs idiomatic API patterns, thorough docs/examples, strong types, testable APIs, and test coverage.
    - Relevance: Directly answers how to bias Rust agents toward good Rust.

16. Microsoft, "Pragmatic Rust Guidelines - Agents & LLMs"
    - URL: https://microsoft.github.io/rust-guidelines/agents/index.html
    - Retrieved: 2026-06-20
    - Finding: The guidelines provide condensed versions intended for LLM consumption.
    - Relevance: Supports vendoring or referencing an agent-consumable Rust guideline layer.

17. Microsoft, "Pragmatic Rust Guidelines - all.txt"
    - URL: https://microsoft.github.io/rust-guidelines/agents/all.txt
    - Retrieved: 2026-06-20
    - Finding: Agent-ready single-file Rust guidance includes application errors, docs, FFI, performance, safety/unsafe, naming, and other idiom rules.
    - Relevance: Candidate upstream material for a `rust-guidelines` skill, subject to licensing and size decisions.

18. Rust Async Book
    - URL: https://rust-lang.github.io/async-book/
    - Retrieved: 2026-06-20
    - Finding: Useful async Rust reference, but the page notes it is undergoing a rewrite and is rough/incomplete in places.
    - Relevance: Use for async fundamentals, but do not treat as the only current async-Rust authority.

19. Corrode.dev, "The State of Async Rust: Runtimes"
    - URL: https://corrode.dev/blog/async/
    - Retrieved: 2026-06-20
    - Finding: Recent ecosystem discussion of async Rust runtimes and tradeoffs.
    - Relevance: Useful secondary context for a future `rust-async-concurrency-reviewer`.

20. WyeWorks, "Async Rust: When to Use It and When to Avoid It"
    - URL: https://www.wyeworks.com/blog/2025/02/25/async-rust-when-to-use-it-when-to-avoid-it/
    - Retrieved: 2026-06-20
    - Finding: Async Rust is best for I/O concurrency; avoid reflexively using it for CPU-heavy/simple workloads, and remember binary-size/runtime overhead.
    - Relevance: Useful practical rule for async Rust agent prompts.

21. Corrode.dev, "Learning Material for Idiomatic Rust"
    - URL: https://corrode.dev/blog/idiomatic-rust-resources/
    - Retrieved: 2026-06-20
    - Last updated: 2026-01-01
    - Finding: Curated idiomatic Rust resources list.
    - Relevance: Good supplemental source discovery, not a primary rule source.

22. Microsoft/rust-guidelines GitHub repository
    - URL: https://github.com/microsoft/rust-guidelines
    - Retrieved: 2026-06-20
    - Finding: Source repository for the Pragmatic Rust Guidelines; contribution criteria require practical applicability and broad agreement among experienced Rust developers.
    - Relevance: Helps judge maturity and provenance.

23. Medium/Rustaceans, "Implementing Microsoft's Rust Guidelines for AI Coding Agents"
    - URL: https://medium.com/rustaceans/implementing-microsofts-rust-guidelines-for-ai-coding-agents-bf985dd60fc6
    - Retrieved: 2026-06-20
    - Finding: Secondary article claiming Microsoft produced agent-optimized Rust guidelines and discussing local setup for AI coding assistants.
    - Relevance: Trend/supporting evidence only; prefer Microsoft primary source.

24. Azure SDK for Rust, `AGENTS.md`
    - URL: https://github.com/Azure/azure-sdk-for-rust/blob/main/AGENTS.md
    - Retrieved: 2026-06-20
    - Finding: Example of a large Rust project using explicit agent guidance.
    - Relevance: Useful later as a pattern sample for repo-specific Rust product agents.

25. GitHub Gist, "Rust AGENTS.md (2026-02-23)"
    - URL: https://gist.github.com/minimaxir/068ef4137a1b6c1dcefa785349c91728
    - Retrieved: 2026-06-20
    - Finding: Community Rust agent-guidance sample.
    - Relevance: Treat as inspiration only; not a primary authority.

26. zfhuang99, "Learnings from 100K Lines of Rust with AI"
    - URL: https://zfhuang99.github.io/rust/claude%20code/codex/contracts/spec-driven%20development/2025/12/01/rust-with-ai.html
    - Retrieved: 2026-06-20
    - Finding: Practitioner report that Rust AI workflows improve when implementation specs are critiqued by another model/agent before coding.
    - Relevance: Supports an adversarial review/plan-review loop for nontrivial Rust work.

27. Martin Fowler, "Context Engineering for Coding Agents"
    - URL: https://martinfowler.com/articles/exploring-gen-ai/context-engineering-coding-agents.html
    - Retrieved: 2026-06-20
    - Published: 2026-02-25
    - Finding: Current coding-agent practice is increasingly organized around context configuration features such as rules, skills, and specs rather than prompt text alone.
    - Relevance: Supports the repo architecture of canonical agents plus reusable `skills/` rubrics.

28. Foojay, "5 Best Practices for Working with AI Agents, Subagents, Skills and MCP"
    - URL: https://foojay.io/today/best-practices-for-working-with-ai-agents-subagents-skills-and-mcp/
    - Retrieved: 2026-06-20
    - Published: 2026-03-30
    - Finding: Recent practitioner guidance emphasizes precise agent behavior, context isolation/reuse, MCP security, and explicit quality/security guardrails.
    - Relevance: Supports narrow language specialists, shared rubrics, and conservative tool access.

29. Rust Users Forum, "SKILLS.md for Rust development"
    - URL: https://users.rust-lang.org/t/skills-md-for-rust-development/140098
    - Retrieved: 2026-06-20
    - Published: 2026-05-14
    - Finding: Rust practitioners are actively using skill files to steer AI coding tools toward idiomatic Rust and better crate/workspace structure.
    - Relevance: Recent field signal that a Rust skill/rubric layer is the right artifact, not just a subagent prompt.

30. arXiv, "Documentation-Guided Agentic Codebase Migration from C to Rust"
    - URL: https://arxiv.org/html/2605.14634v3
    - Retrieved: 2026-06-20
    - Published: 2026-05
    - Finding: RustPrint uses repository-level documentation as a shared representation for planning, translating, comparing behavior, and repairing failures during C-to-Rust migration.
    - Relevance: Supports product/repo agents carrying local docs and verification contracts while language agents carry Rust idiom.

31. GitHub Gist, "Agent Guidelines for Rust Code Quality"
    - URL: https://gist.github.com/minimaxir/068ef4137a1b6c1dcefa785349c91728
    - Retrieved: 2026-06-20
    - Updated: 2026-02-23
    - Finding: Community Rust `AGENTS.md` guidance stresses concrete quality rules for AI agents working in Rust.
    - Relevance: Supplemental pattern source; not a primary authority.

## Findings

### General Coding-Agent Findings

1. Best coding agents are not giant personalities; they are narrow roles with clear triggers, bounded tools, and explicit output contracts.
2. Subagents should be used when their work would flood the main context or when the same specialist role recurs.
3. The `description` field is load-bearing: it is the router. It must say "Use when..." with enough specificity to trigger correctly and avoid noisy delegation.
4. Agent quality depends on context engineering, not just prompt prose. The product should separate:
   - stable language/rubric context,
   - repo/product context,
   - task-specific context,
   - tool outputs and verification evidence.
5. Verification commands belong in the agent prompt. A coding agent that cannot name its proof command is not finished.
6. Tool access should follow the job:
   - reviewer/explorer agents: read-only plus test/build commands when needed,
   - implementer agents: edit rights plus exact validation commands,
   - safety/unsafe/security agents: read-heavy, conservative, with explicit escalation rules.
7. Product agents should compose language expertise, not duplicate it. Product agents know the repo/domain; language agents know idiom and failure modes.
8. Vendored agents/skills should enter through the same canonical registry only after source, license, maintenance, and trigger behavior are reviewed.

### Rust-Agent Findings

1. The first Rust agent should be `rust-idiom-reviewer`, not a broad `rust-expert`.
2. The shared Rust rubric should draw primarily from Rust API Guidelines and Microsoft Pragmatic Rust Guidelines.
3. The Rust agent should be allergic to "compiles but unidiomatic" code:
   - primitive obsession,
   - needless `Arc<Mutex<_>>`,
   - `String` ownership where `&str` or borrowed slices suffice,
   - Java-style `Manager`/`Service` type names,
   - broad traits or `dyn` where concrete/generic types are clearer,
   - `anyhow` in public library APIs,
   - async for CPU-bound/simple work,
   - `unsafe` without a safety invariant.
4. Rust agents should prefer observable behavior tests and exact workspace gates over narrow helper scripts.
5. Rust review output should be severity-ranked and evidence-backed, not an essay.
6. Rust implementer agents should be stricter than reviewers:
   - no new dependencies without justification,
   - no `unsafe` without documented safety and tests,
   - no API churn without checking call sites,
   - no "fix clippy by silencing clippy" unless the `#[expect]` reason is good.
7. Async Rust deserves its own specialist. It is a common source of plausible-looking mistakes: blocking in async, runaway task spawning, cancellation blindness, CPU-heavy futures without yield points, and runtime leakage through APIs.
8. Unsafe/FFI deserves its own specialist. It should require safety comments, module-boundary soundness review, adversarial tests, and Miri when applicable.

## Recommended Agent Family

### Shared Language Rubric Layer

Create a reusable Rust rubric/skill before or alongside agents:

```text
skills/rust-guidelines/
  SKILL.md
  references/
    rust-api-guidelines.md
    pragmatic-rust-guidelines-notes.md
    async-rust-notes.md
```

Implemented in this repo as `skills/rust-guidelines/SKILL.md`. It summarizes and links to source guidance rather than vendoring Microsoft `all.txt`.

### Rust Language Expert Agents

1. `rust-idiom-reviewer`
   - Implemented.
   - Read/review oriented.
   - Bias: idiomatic API shape, ownership, error handling, tests, clippy/fmt.

2. `rust-implementer`
   - Implemented.
   - Edit-capable.
   - Bias: minimal, test-backed, idiomatic implementation.

3. `rust-api-designer`
   - Implemented.
   - Bias: type design, public API ergonomics, error model, feature flags, semver/future-proofing.

4. `rust-async-concurrency-reviewer`
   - Implemented.
   - Bias: runtime boundaries, cancellation, blocking, backpressure, yield points, task lifetimes.

5. `rust-unsafe-ffi-auditor`
   - Implemented.
   - Bias: no unsound safe APIs, explicit invariants, Miri/adversarial tests when possible.

6. `rust-performance-profiler`
   - Implemented.
   - Bias: identify hot path, benchmark before optimizing, avoid needless allocation/cloning, choose throughput/latency tradeoffs explicitly.

### Future Language Expert Pattern

Use the same shape for Python, Scala, Java, Kotlin, Swift, Terraform, etc.:

```text
<language>-idiom-reviewer
<language>-implementer
<language>-api-designer
<language>-concurrency-or-runtime-specialist
<language>-migration-or-interoperability-specialist
```

Do not force every language into exactly the same slots. Terraform likely wants module/security/state specialists; Swift likely wants SwiftUI/AppKit/iOS lifecycle specialists; Scala likely wants typelevel/effect-system and JVM interop specialists.

### Product-Agent Layer

Product agents should compose language agents:

```text
hippo-rust-maintainer
cdc-rust-maintainer
whistlepost-rust-web-maintainer
```

These should encode:

- repo layout,
- exact verification gates,
- deployment/CI quirks,
- domain language,
- known failure patterns,
- when to delegate to `rust-idiom-reviewer` or `rust-async-concurrency-reviewer`.

## Draft `rust-idiom-reviewer` Agent

```markdown
---
name: rust-idiom-reviewer
description: Use when reviewing Rust code for idiomatic API design, ownership, error handling, async correctness, unsafe usage, performance traps, or maintainability.
model: inherit
tools: Read, Bash
color: orange
---

You are a senior Rust reviewer focused on idiomatic, maintainable Rust.

Before judging, inspect the actual diff and crate structure. Prefer coherent repo-local conventions, but push back when they fight Rust idioms.

Review against:
- Rust API Guidelines.
- Microsoft Pragmatic Rust Guidelines.
- rustfmt and clippy expectations.
- Strong types over primitive obsession.
- Explicit error semantics.
- Minimal, justified unsafe.
- Async only when it buys real concurrency.
- Tests that prove observable behavior.

Bias toward:
- borrowed inputs over owned allocation when ownership is unnecessary,
- domain newtypes for semantic distinctions,
- public `Debug` where appropriate,
- builders for genuinely complex construction,
- clear module docs and public API examples,
- `#[expect]` with a reason instead of broad lint suppression,
- library-specific error types for library APIs,
- `anyhow` or `eyre` only in application boundaries.

Be suspicious of:
- `Arc<Mutex<_>>` as a lifetime escape hatch,
- `String`/`Vec` cloning without a reason,
- `Manager`, `Service`, or `Factory` names that hide the domain,
- async around CPU-heavy or simple sequential work,
- blocking calls inside async tasks,
- `unsafe` without a safety invariant,
- changing public APIs without checking call sites.

When available, run or request:
- `cargo fmt --all -- --check`
- `cargo clippy --workspace --all-targets -- -D warnings`
- `cargo test --workspace`
- repo-specific gates after confirming their coverage.

Output severity-ranked findings first. Each finding needs file/line evidence, why it matters, and the idiomatic Rust direction.
```

## Open Questions

1. Resolved: commit the Rust starter family now, not only `rust-idiom-reviewer`.
2. Resolved: summarize and link Microsoft `all.txt` for now. The upstream repo is MIT licensed, but link-only keeps this repo compact and avoids stale vendored guidance.
3. Resolved: add a first-class `skills/` concept now and validate it alongside agents.
4. Open: Rust product agents can be hand-authored for known high-value repos after the public language expert layer lands.
5. Resolved: use `<language>-idiom-reviewer`; it is more specific and routes better than `<language>-expert-reviewer`.

## Implemented Artifacts

- `skills/rust-guidelines/SKILL.md`
- `agents/rust-idiom-reviewer/agent.md`
- `agents/rust-implementer/agent.md`
- `agents/rust-api-designer/agent.md`
- `agents/rust-async-concurrency-reviewer/agent.md`
- `agents/rust-unsafe-ffi-auditor/agent.md`
- `agents/rust-performance-profiler/agent.md`
- `schema/skill.schema.json`
- Registry validation for `skills/<name>/SKILL.md`
- Tests proving the required Rust agent inventory and Rust skill exist

## Handoff Notes

- Do not collapse language expert agents and product agents into one layer.
- Build `rust-idiom-reviewer` first; it has the best value-to-risk ratio.
- Keep agent prompts concrete. Avoid "best coder in the world" fluff.
- Treat source-backed verification as part of agent identity.
- For Rust, "idiomatic" means API shape, error model, ownership, testing, docs, and toolchain gates, not just `cargo fmt`.
- If implementing next, use TDD around the registry validator if adding new metadata fields or skill support.
