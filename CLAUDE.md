# CLAUDE.md

This repo stores non-sensitive agent definitions and shared language rubrics only.

Do not add work secrets, customer-specific implementation details, credentials, tokens, or private infrastructure names to `agents/` or `skills/`. Keep sensitive definitions in their owner's private configuration outside this public repository.

Language experts should stay general and reusable. Product-focused agents may mention public repo structure and verification gates, but private deployment details belong in encrypted local configuration.

Before claiming changes are complete, run `just check` (tests, validation, and all configured emit targets). If `just` is unavailable, run its explicit `uv run` commands. `build/` is ignored local scratch output; installation emits from source in memory. Editing or checking this repository does not require installation into live tool configuration.
