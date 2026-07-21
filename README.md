# agents

Canonical registry for non-sensitive AI agent definitions and reusable language rubrics.

This public snapshot contains general-purpose agents, reusable skills, registry tooling,
and synthetic evaluation fixtures. Employer-specific agents, business context, private
infrastructure details, and credentials are intentionally excluded.

The source format for agents is Claude-native subagent Markdown: YAML frontmatter plus a body in `agents/<name>/agent.md`. Claude can consume this shape directly. Codex emission is intentionally tiny and conservative until the user-agent load path is verified.

Shared reusable guidance lives under `skills/<name>/SKILL.md`. Language expert agents should refer to a shared skill/rubric instead of duplicating the whole checklist in every prompt.

Sensitive work-domain agents do not belong in this repository. Store those as age-encrypted chezmoi-managed files in the dotfiles repo.

## License

MIT. See [LICENSE](LICENSE).

## Language Expert Pattern

Language expert agents should be narrow and router-friendly:

- `<language>-idiom-reviewer`
- `<language>-implementer`
- `<language>-api-designer`
- runtime or concurrency specialists where the language warrants them
- safety, interop, migration, or performance specialists where the risk justifies a separate context window

Rust currently has:

- `rust-idiom-reviewer`
- `rust-implementer`
- `rust-api-designer`
- `rust-async-concurrency-reviewer`
- `rust-unsafe-ffi-auditor`
- `rust-performance-profiler`

All Rust agents share `skills/rust-guidelines/SKILL.md`, which summarizes and links to the Rust API Guidelines, Microsoft Pragmatic Rust Guidelines, and async Rust references.

Product-focused agents should compose language expertise with repo-specific context: layout, domain language, exact gates, CI/deploy quirks, and known failure modes. Do not bake product secrets into public language agents.

## Commands

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
agents/
  <name>/agent.md
skills/
  <name>/SKILL.md
schema/
  agent.schema.json
  skill.schema.json
agent_registry/
  agents.py
  codex.py
mining/
  queries.sql
  mine_hippo.py
```
