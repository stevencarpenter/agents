---
name: rust-guidelines
description: Use when writing, reviewing, or designing Rust code where idiomatic APIs, ownership, async, unsafe, performance, tests, or public crate ergonomics matter.
---

# Rust Guidelines

Use this as the shared Rust language rubric for agents. Prefer repo-local conventions when they are deliberate and documented, but push back when they produce unidiomatic, fragile, or unsound Rust.

## Source Of Truth

- Rust API Guidelines: https://rust-lang.github.io/api-guidelines/checklist.html
- Microsoft Pragmatic Rust Guidelines: https://microsoft.github.io/rust-guidelines/
- Microsoft agent-ready Rust guidance: https://microsoft.github.io/rust-guidelines/agents/all.txt
- Async Rust Book: https://rust-lang.github.io/async-book/

The Microsoft `rust-guidelines` repository is MIT licensed. This repo summarizes and links to those guidelines rather than vendoring `all.txt` for now.

## Core Rubric

- Prefer strong domain types, newtypes, enums, and validated constructors over primitive obsession.
- Prefer borrowed inputs such as `&str`, `&[T]`, and `impl AsRef<Path>` when ownership is unnecessary.
- Keep ownership transfer explicit. Do not clone `String`, `Vec`, `Arc`, or large values without a reason.
- Use concrete types and generics before `dyn` unless dynamic dispatch is intentional.
- Avoid vague Java-style names such as `Manager`, `Service`, `Factory`, and `Util` when a domain name exists.
- Public APIs should be hard to misuse: clear argument types, builders for genuinely complex construction, and additive feature design.
- Public types should implement `Debug` where useful and expose canonical docs or examples for nontrivial APIs.
- Libraries should expose domain-specific error types; applications may use `anyhow` or `eyre` at the boundary.
- Lint exceptions should use `#[expect(..., reason = "...")]` or an equivalent documented reason, not broad suppression.
- `unsafe` requires a stated invariant, a narrow boundary, sound safe APIs, and tests. Use Miri when it is applicable and available.
- Async should buy real I/O concurrency or scheduling value. Avoid blocking calls inside async tasks, runaway spawning, cancellation blindness, and runtime details leaking through public APIs.
- Performance work starts with a hot path, profile, or benchmark. Do not optimize by folklore.

## Verification

Use exact repo-native gates first. For ordinary Rust work, request or run `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings`, and `cargo test --workspace` when they fit the repo.

## Adversarial Checklist

Push back when a change or suggestion hits these traps:

- **`block_in_place` / `spawn_blocking` in async** — blocking the async executor or parking a thread without a stated reason; prefer async I/O or an explicit blocking pool with bounded concurrency.
- **`select!` without cancellation** — spawned tasks or channels left running after a branch wins; tie work to `tokio::select!` cancellation or explicit abort handles.
- **`#[allow(...)]` without `#[expect(..., reason = "...")]`** — broad lint suppression instead of a narrow, documented exception.

## Output Contract

When reviewing, lead with severity-ranked findings and concrete file/line evidence. Each finding should explain why the current Rust shape is risky and name the more idiomatic direction.

When implementing, make the smallest coherent change, update or add tests for observable behavior, and record the exact proof command.
