# CLAUDE.md

This repo stores non-sensitive agent definitions and shared language rubrics only.

Do not add work secrets, customer-specific implementation details, credentials, tokens, or private infrastructure names to `agents/` or `skills/`. Sensitive agents should be stored age-encrypted in chezmoi, not committed here.

Language experts should stay general and reusable. Product-focused agents may mention public repo structure and verification gates, but private deployment details belong in encrypted local configuration.

Before claiming changes are complete, run `just check` (tests + validate + emit to all four targets). `build/` is a gitignored local scratch output for browsing emitted agents — nothing in the deploy path reads it; `install`/the chezmoi hook emit from source in-memory.
