# Contributing

Thanks for contributing. Bug reports, focused improvements, new reusable agents,
and corrections to existing guidance are welcome.

## Before opening a change

- Keep agents and skills general-purpose and free of employer, customer, or private
  infrastructure details.
- Do not include credentials, tokens, proprietary material, or generated output from
  `build/`.
- Prefer narrow agents with explicit routing descriptions over broad assistants.

## Development

The project uses Python 3.14 and `uv`:

```sh
uv sync
uv run python -m unittest discover -s tests
uv run python -m agent_registry.cli validate
uv run python -m agent_registry.cli emit-claude
uv run python -m agent_registry.cli emit-codex
uv run python -m agent_registry.cli emit-opencode
uv run python -m agent_registry.cli emit-copilot
```

Generated files under `build/` are ignored and should not be committed.

## Pull requests

Explain what changed, why it is useful, and how it was verified. Keep unrelated
changes in separate pull requests. By contributing, you agree that your contribution
is licensed under the repository's MIT License.
