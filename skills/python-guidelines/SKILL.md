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

- Type every public signature using syntax supported by the target runtime. Use quoted forward references or `from __future__ import annotations` where runtime evaluation requires them; prefer `X | None` on supported Python versions.
- Use `TypedDict` for known dictionary shapes, including JSON boundaries; use `dataclass` or `NamedTuple` when objects fit the runtime model. Keep simple mappings as mappings instead of adding conversion layers.
- Use `pathlib.Path` for filesystem paths, never raw string concatenation.
- Raise specific exceptions (`ValueError`, `FileNotFoundError`, domain classes). Never `except:` bare and never `except Exception: pass`. Let exceptions you can't handle propagate.
- Subprocess: pass args as a list, never `shell=True` with interpolated input. Use `check=True` or handle expected nonzero statuses explicitly. Capture output when the caller consumes it; inherit streams for interactive commands.
- No mutable default arguments. No module-level mutable global state used as a cache without a reason.
- Prefer `uv run` for invocation in uv-managed repos. Avoid new runtime dependencies when the stdlib suffices.

## Tests

- Match the repo's framework (`unittest.TestCase` or pytest) — don't mix.
- Test the contract: inputs → outputs and error conditions, not internal call sequences.
- Use `tempfile.TemporaryDirectory` or the existing framework's temporary-path fixture for filesystem tests; never write to the project tree.

## Verification

Run the repo's exact gates and relevant tests using its existing runner. Use `uv run` in uv-managed repos; run ruff, mypy, pytest, or unittest only as configured. Do not add tooling to satisfy this rubric.

## Output Contract

When reviewing, lead with severity-ranked findings with file/line evidence: correctness > type safety > resource safety > testability > performance > style. When implementing, make the smallest coherent change, add tests for observable behavior, and record the exact proof command.
