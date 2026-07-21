# Survey: Claude Code agent specs for technical writing, slide design, and data engineering

Date: 2026-06-22
Method: fan-out web search (6 angles) → fetched 21 sources → 99 candidate claims → 25
verified with 3-vote adversarial checking (kill on 2/3 refutes). 21 confirmed, 4 killed.

## Headline

There is **no benchmark or leaderboard for Claude Code subagent specs**. "Best" here means
GitHub stars (adoption proxy), recency, and prompt quality — nothing more rigorous exists. And
**no widely-adopted subagent covers the data-engineering combination requested** (lakehouse +
realtime + AI/ML as a dedicated agent). The strongest move was to author specs matching this
registry's conventions, borrowing structural ideas from the best existing specs.

## Collections (ranked by adoption)

- **wshobson/agents** — ~37.1k★, 192 agents; files carry `model: inherit`.
  https://github.com/wshobson/agents
  - *Killed (0-3):* the specific docs roster (`docs-architect` opus / `tutorial-engineer` sonnet
    / `reference-builder` haiku / `api-documenter` / `mermaid-expert`) could not be verified at the
    cited path. Treat as unconfirmed.
  - *Killed (0-3):* "data engineering has only generic agents, none naming Delta/Iceberg/Kafka" —
    could not be confirmed as stated.
- **VoltAgent/awesome-claude-code-subagents** — ~22.3k★.
  https://github.com/VoltAgent/awesome-claude-code-subagents
  - `categories/05-data-ai/data-engineer.md`: `tools: Read, Write, Edit, Bash, Glob, Grep`,
    `model: sonnet`; body names Delta Lake / Hudi / Iceberg / Databricks lakehouse. (confirmed)
  - Also ships `mlops-engineer.md` (sonnet), `ml-engineer`, `ai-engineer`, vector specialists.
  - `categories/08-business-product/technical-writer.md` — the tech-writing spec.
- **supatest-ai/awesome-claude-code-sub-agents** — one `documentation-specialist` (no model field).
  https://github.com/supatest-ai/awesome-claude-code-sub-agents
  - *Killed (0-3):* its "40-50 agents / 10 categories" self-description didn't verify.

## Per domain

### Technical writing — thin
- VoltAgent `technical-writer.md`; supatest `documentation-specialist`.
- Practitioner writeup: Google Cloud / Medium, "Supercharge tech writing with Claude Code
  subagents and Agent Skills."
  https://medium.com/google-cloud/supercharge-tech-writing-with-claude-code-subagents-and-agent-skills-44eb43e5a9b7

### Slide / presentation design — best *real* subagents
- **seulee26/mckinsey-pptx** → `agents/mckinsey-slide-agent.md` — ~480★;
  `tools: Read, Write, Edit, Bash, Glob, Grep`, `model: inherit`; system prompt emphasizes
  selecting and **defending** the template choice. (confirmed)
  https://raw.githubusercontent.com/seulee26/mckinsey-pptx/main/agents/mckinsey-slide-agent.md
- **tristan-mcinnis/pptx-from-layouts-skill** — 3 subagents, all `model: sonnet`, python-pptx.
  https://github.com/tristan-mcinnis/pptx-from-layouts-skill
- The popular ones are **Skills, not subagents**: `zarazhangrui/frontend-slides` (~22.5k★, HTML/CSS
  decks), `robonuggets/marp-slides` (~246★, Markdown/Marp).

### Data engineering (lakehouse / realtime / AI-ML) — gap
- No subagent is *dedicated* to lakehouse + streaming + AI/ML. Generic `data-engineer` /
  `mlops-engineer` exist (above).
- **databricks/databricks-agent-skills** — official Databricks repo (~168★) covering Unity Catalog
  / lakehouse / pipelines — but ships **Skills**, not subagents (near-miss).
  https://github.com/databricks/databricks-agent-skills

## What was authored from this (in-tree)

- `agents/technical-writer/agent.md` — lean How-to agent; applies the Diátaxis rubric (below) and
  defers the Reference quadrant (README/API/ADR/runbook) to `documentation-writer`.
- `agents/slide-designer/agent.md` — storyline-first, action titles, message-per-slide, deliberate
  Marp/Slidev/reveal/python-pptx format choice (mckinsey-slide-agent's template-defense idea).
- `agents/data-engineer/agent.md` + `skills/data-engineering-guidelines/SKILL.md` — fills the
  confirmed gap: lakehouse (Delta/Iceberg, medallion, compaction, MERGE/CDC), realtime (Kafka,
  Structured Streaming/Flink, watermarks, exactly-once), AI/ML data (feature stores, point-in-time
  correctness, vector/RAG), quality, governance, cost. Vendor-general, no private infra.

### Follow-up (2026-06-23): Diátaxis deepening + Figma-first diagrams

- `skills/technical-writing-guidelines/SKILL.md` — shared Diátaxis rubric (two axes, four modes,
  mode-detection, anti-mixing rule, per-mode quality bars, "every doc needs a why"). `technical-writer`
  and `documentation-writer` both apply it; the agents stay lean.
- `skills/diagramming-guidelines/SKILL.md` — Figma FigJam is the house diagram standard; Mermaid and
  Excalidraw are demoted to last-resort fallbacks. Diagram deliverable = editable board link +
  exported snapshot + prose. Referenced by technical-writer, slide-designer, documentation-writer,
  and data-engineer; those agents carry the Figma MCP tools so they can render boards (Claude target;
  codex/opencode/copilot emit drops unknown tools without breaking).
