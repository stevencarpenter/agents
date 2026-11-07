# Session-routing context

`generate_context.py` builds a small Markdown block for injection into a
Claude Code session at start-up, via a SessionStart hook that the dotfiles
(`~/.dotfiles`, managed by dfm) wire into Claude settings.

## Why this exists, and why it's small

Claude Code already injects the full agent list (names, descriptions,
tools) and the full skill list into the system prompt every session. A
hook that re-lists agents/skills duplicates that at negative value. This
script emits only what injection does not provide: hand-curated
disambiguation rules for overlapping agents, cross-family shared-rubric
overlap, declared-vs-installed staleness on two independent pipelines
(the agents repo and the personal skills manifest), and the live MCP server
inventory.

A pairing table and an MCP priority map were cut: they restated agent names
and the user's global CLAUDE.md. The declared-vs-installed agent diff stays
because it has caught real staleness.

## Deployment

- This script lives in the agents repo (canonical source), not dotfiles,
  because it needs direct filesystem access to `agents/*/agent.md`.
- `routing-overlay.md` (sibling file) holds the hand-curated
  disambiguation rules, a judgment call no config states, kept separate
  from the generator so it isn't clobbered by re-generation and doesn't
  need a code change to edit.
- The cache (`~/.cache/agent-routing/context.md`) is written by the
  dotfiles script `scripts/install-agent-registry.sh`, right after it runs
  `agent_registry.cli install` from the side-channel clone of this repo at
  `~/.local/share/agent-registry`. It runs this script and moves the output
  into place atomically. No new trigger plumbing.
- `~/.claude/hooks/emit-routing-context.sh` (dotfiles:
  `home/.claude/hooks/emit-routing-context.sh`) is the actual SessionStart
  hook; it only `cat`s the cache (~10ms, no Python startup cost per
  session). `dfm-module-agents.toml` contributes the hook entry to the
  Claude settings resource, so a host has it only when its dfm profile
  selects the `agents` module.
- On a host whose profile does not select `agents`, the hook entry is
  absent: no wasted exec, no cache to go stale, no empty-context noise.
  Every dotfiles-path read in this script is also best-effort standalone,
  so running it directly (`python3 tools/routing/generate_context.py`)
  still produces a valid, smaller block on a box with no dotfiles applied
  at all. See `test_render_omits_absent_optional_sections` in
  `tests/test_routing_context.py`.
- The skills manifest and the identity overlay are read from the deployed
  links `~/.config/skills/skills-master.json` and
  `~/.config/skills/machine/<identity>.json`. The identity comes from
  `DFM_IDENTITY` when set (the same seam the dotfiles sync scripts use),
  else from the single overlay the identity module links there.

## Known limitations (not solved here)

- Targets the top-level Claude Code session only. Subagents dispatched via
  Task do not automatically get the parent's SessionStart output
  re-injected. If per-subagent routing matters, this cache would need to
  be surfaced a different way (e.g. read explicitly by name, or baked into
  the dispatching agent's own prompt).
- Codex and OpenCode have no equivalent SessionStart mechanism wired up
  here; this is Claude-Code-only for now.
- There is no central table of hosts and their capabilities (dfm profiles
  are per host and nothing enumerates them), so the block cannot say which
  other machines lack the agents capability.
- The disambiguation rules in `routing-overlay.md` are hand-written prose
  with no structured source (no `disambiguates_with:` frontmatter field
  exists on agents today). If a new ambiguous family shows up, someone has
  to remember to add a rule by hand. The generator does nothing to detect
  that one is needed.
