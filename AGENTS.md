# AGENTS.md

This is a Python CLI registry. Source definitions live in `agents/`, shared
rubrics in `skills/`, and emission/validation code in `agent_registry/`.
There is no application server or web UI.

Use `uv` with the repository's pinned Python. The registry has no runtime
dependencies; the separate `eval/` project has its own environment.

Run `just check` before claiming completion. It runs tests, validation, and all
configured emit targets. If `just` is unavailable, run the commands from the
`justfile` explicitly with `uv run`. Validation checks skill references,
source contracts, secret-shaped content, and control characters. Do not add
linters or type checkers merely because a language rubric mentions them.

Emission writes ignored scratch output under `build/`. It does not install
definitions into live tool configuration. Use temporary directories for
tests that exercise installation or modify source fixtures.

Inspect version-control state before editing. In a Jujutsu-managed checkout,
follow `skills/jj-guidelines/SKILL.md` and the local `just jj-*` helpers.
Otherwise use the repository's Git workflow. Check tool availability rather
than assuming a cloud or local machine has a particular executable.

Keep sensitive definitions, credentials, customer details, and private
infrastructure names outside this public repository. Read `CLAUDE.md` for
the shared scope and completion requirements.
