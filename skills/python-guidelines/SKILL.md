---
name: python-guidelines
description: Use when writing, reviewing, or designing Python code where typing, error handling, resource safety, subprocess use, or test design matter.
---

# Python Guidelines

Shared Python rubric for agents. Prefer repo-local conventions when they are deliberate and documented; push back when they produce unsafe, untyped, or untestable Python.

## Source Of Truth

- PEP 8 (style), PEP 484 / PEP 604 (typing), PEP 257 (docstrings)
- The repo's own `pyproject.toml` tool config (ruff, mypy, pytest) — this overrides general preference

## Core Rubric

- Type every public signature. Use `from __future__ import annotations` for forward refs on Python < 3.12. Use `X | None`, not `Optional[X]`, on modern runtimes.
- Model structured data with `dataclasses` (or `NamedTuple`) over bare dicts; reserve `TypedDict` for genuinely dynamic shapes.
- Use `pathlib.Path` for filesystem paths, never raw string concatenation.
- Raise specific exceptions (`ValueError`, `FileNotFoundError`, domain classes). Never `except:` bare and never `except Exception: pass`. Let exceptions you can't handle propagate.
- Subprocess: pass args as a **list**, never `shell=True` with interpolated input. Use `check=True` and capture `stdout`/`stderr` explicitly. Never ignore the return value.
- No mutable default arguments. No module-level mutable global state used as a cache without a reason.
- Prefer `uv run` for invocation in uv-managed repos. Avoid new runtime dependencies when the stdlib suffices.

## Tests

- Match the repo's framework (`unittest.TestCase` or pytest) — don't mix.
- Test the contract: inputs → outputs and error conditions, not internal call sequences.
- Use `tempfile.TemporaryDirectory` for filesystem tests; never write to the project tree.

## Verification

Run the repo's exact gates first. Typical: `uv run python -m unittest discover -s tests` (or `pytest`), `uv run ruff check .`, `uv run mypy .`.

## Output Contract

When reviewing, lead with severity-ranked findings with file/line evidence: correctness > type safety > resource safety > testability > performance > style. When implementing, make the smallest coherent change, add tests for observable behavior, and record the exact proof command.
