# Session-routing context

`generate_context.py` builds a small Markdown block for injection into a
Claude Code session at start-up, via a chezmoi-managed SessionStart hook.

## Why this exists, and why it's small

Claude Code already injects the full agent list (names, descriptions,
tools) and the full skill list into the system prompt every session. A
hook that re-lists agents/skills duplicates that at negative value. This
script emits only what injection does not provide: hand-curated
disambiguation rules for overlapping agents, cross-family shared-rubric
overlap, declared-vs-installed staleness on two independent pipelines
(the agents repo and the personal skills manifest), the live MCP server
inventory, and per-machine capability deltas.

An earlier version also carried an implementer/reviewer pairing table and
a hand-curated MCP priority quick-map. Both were cut after a judged
three-way prototype bakeoff (static pre-generation vs. live dynamic scan
vs. this curated-router approach) found they mostly restated facts already
visible in agent names or in the user's global CLAUDE.md (which already
states MCP tool priority — `codegraph` over grep, `mcp__idea__*` over raw
Read, etc.). The bakeoff also surfaced the single highest-value fact in
this whole block: a live diff of the canonical agents repo against what's
actually installed on the machine (`~/.claude/agents`), which caught a
real week-long staleness bug (34 installed vs. 41 canonical) during the
session that built this.

## Deployment

- This script lives in the agents repo (canonical source), not dotfiles,
  because it needs direct filesystem access to `agents/*/agent.md`.
- `routing-overlay.md` (sibling file) holds the hand-curated
  disambiguation rules — a judgment call no config states, kept separate
  from the generator so it isn't clobbered by re-generation and doesn't
  need a code change to edit.
- The cache is written by a step appended to the chezmoi
  `run_after_sync-agents.sh.tmpl` hook, right after it fans agents out to
  `~/.claude/agents` — piggybacking on an event that already runs on every
  `chezmoi apply` that touches the agents repo. No new trigger plumbing.
- `~/.claude/hooks/emit-routing-context.sh` (chezmoi:
  `dot_claude/hooks/executable_emit-routing-context.sh`) is the actual
  SessionStart hook; it only `cat`s the cache (~10ms, no Python startup
  cost per session). Wired into `dot_claude/modify_settings.json.tmpl`,
  gated on the `agents` machine capability the same way the `hippo` hook
  is gated on personal-only.
- On a machine with `agents=false` (work-mac, lab-mac as of this writing),
  the SessionStart hook entry is omitted entirely by the template — no
  wasted exec, no cache to go stale, no empty-context noise. Every
  chezmoi-path read in this script is also best-effort standalone, so
  running it directly (`python3 tools/routing/generate_context.py`) still
  produces a valid, smaller block on a box with no dotfiles applied at
  all — see `test_render_omits_absent_optional_sections` in
  `tests/test_routing_context.py`.

## Known limitations (not solved here)

- Targets the top-level Claude Code session only. Subagents dispatched via
  Task do not automatically get the parent's SessionStart output
  re-injected — if per-subagent routing matters, this cache would need to
  be surfaced a different way (e.g. read explicitly by name, or baked into
  the dispatching agent's own prompt).
- Codex and OpenCode have no equivalent SessionStart mechanism wired up
  here; this is Claude-Code-only for now.
- The personal-skills declared-vs-installed check skips `.tmpl` machine
  overlays (can't safely parse Go template syntax as plain JSON without
  `chezmoi execute-template`, which isn't guaranteed available) — it will
  under-count "declared" on a machine whose overlay is template-gated.
- The disambiguation rules in `routing-overlay.md` are hand-written prose
  with no structured source (no `disambiguates_with:` frontmatter field
  exists on agents today). If a new ambiguous family shows up, someone has
  to remember to add a rule by hand — the generator does nothing to detect
  that one is needed.
