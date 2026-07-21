# AGENTS.md

## Cursor Cloud specific instructions

This repo is a pure-Python CLI (`agent_registry`) that validates AI agent
definitions in `agents/`, inlines shared rubrics from `skills/`, and emits
them for Claude/Codex/OpenCode/Copilot. There is no server or web UI; "running
the app" means invoking the CLI.

- Toolchain: managed by `uv` (already on `PATH` via `~/.bashrc`/`~/.profile`).
  The project pins Python 3.14 (`.python-version`) and has **no third-party
  dependencies**, so `uv sync` only provisions the interpreter + `.venv`.
- Standard commands live in `README.md` and the `justfile`. Run them with
  `uv run`, e.g. `uv run python -m unittest discover -s tests`,
  `uv run python -m agent_registry.cli validate`, and the `emit-*` subcommands.
- `validate` is the lint/correctness gate (no ruff/mypy are configured despite
  the rubric text). It fails loudly on dangling `skills:` references,
  secret-shaped content, and control characters.
- `just` is **not** installed; `just check` will not work. Use the explicit
  `uv run ...` commands from `README.md` instead.
- `emit-*` rewrites generated output under `build/`, which is entirely
  gitignored local scratch — nothing in the deploy path reads it, and
  re-running emit never dirties the tracked tree.
- The `justfile` documents a `jj` (jujutsu) workflow, but plain `git` works
  fine and `jj` is not installed.
- To smoke-test the pipeline without touching the tracked tree, point the CLI
  at a temp agents dir while reusing the real skills:
  `uv run python -m agent_registry.cli validate --agents-dir /tmp/x/agents --skills-dir skills`.
