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
- Keep visibility as narrow as possible. Never widen `pub` to silence the compiler; `pub(crate)` is the default ceiling until a caller outside the crate exists.
- Make the smallest coherent diff. No drive-by refactors, renames, import reshuffles, or formatting churn outside the change scope.

## Anti-Slop Checklist

Reject or fix these generated-code debt patterns on sight, whether writing or reviewing:

- `unwrap()`/`expect()` on fallible operations outside tests — propagate with `?` behind a domain error type.
- `.clone()` sprinkled to silence the borrow checker — fix the ownership or borrowing shape; clone only with a stated reason.
- `Arc<Mutex<T>>` used as a lifetime escape hatch instead of an ownership design.
- Lossy `as` casts between numeric types — any cast the target can't represent exactly (narrowing, sign-changing, `u32 as f32`, float→int) silently truncates or saturates; use `From` for infallible widening, `TryFrom` for int↔int narrowing, and explicit range/NaN handling for float↔int (std has no `TryFrom` there).
- `Box<dyn Error>` or `anyhow` erasing error structure inside library code.
- `todo!()`, `unimplemented!()`, dead code, or commented-out blocks left in a delivered change.
- Doc comments that restate the signature (`/// Returns the value` on `fn value(&self) -> T`) — docs should carry semantics, invariants, or examples.
- `Default` impls, public fields, or `From` conversions that hide validation or failure; use validated constructors and `TryFrom`.
- Needless `collect()`, `format!`, or intermediate `Vec`/`String` allocation when an iterator or `&str` would do.
- Re-export sprawl and glob imports (`pub use foo::*`) that make the public surface unreviewable.

## Verification

Use exact repo-native gates first. For ordinary Rust work, request or run `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings`, and `cargo test --workspace` (which includes doc tests) when they fit the repo.

Reach for these only when the repo has them configured or the change justifies introducing them — do not install tooling speculatively:

- `cargo semver-checks` — public API or semver-sensitive changes.
- `cargo miri test` — any new or touched `unsafe`.
- `loom` — lock-free or shared-memory concurrency primitives.
- `cargo machete` / `cargo-udeps` — dependency additions or Cargo.toml changes.
- `cargo audit` / `cargo deny check` — supply-chain policy, when configured.
- `cargo nextest run` — when the repo uses nextest instead of `cargo test`; pair it with `cargo test --doc`, since nextest does not run doc tests.

## Adversarial Checklist

Push back when a change or suggestion hits these traps:

- **`block_in_place` / `spawn_blocking` in async** — blocking the async executor or parking a thread without a stated reason; prefer async I/O or an explicit blocking pool with bounded concurrency.
- **`select!` without cancellation** — spawned tasks or channels left running after a branch wins; tie work to `tokio::select!` cancellation or explicit abort handles.
- **`#[allow(...)]` without `#[expect(..., reason = "...")]`** — broad lint suppression instead of a narrow, documented exception.
- **Detached `tokio::spawn`** — a dropped `JoinHandle` leaks an untracked task; use a `JoinSet`, store the handle, or document why detachment is correct.
- **Lock held across `.await`** — a `std::sync::Mutex` guard (or `tokio::sync::Mutex` guard kept longer than needed) across an await point stalls or deadlocks the executor; restructure or use the async-aware lock deliberately.
- **Unbounded channels** — `mpsc::unbounded_channel` or a huge buffer hides backpressure bugs; size channels to the real workload.
- **Clone-to-compile** — `.clone()` added wherever the borrow checker complained, instead of adjusting lifetimes or ownership.
- **Silent `as` conversion** — `len as u32`, `x as i64` where overflow, truncation, or sign change is possible.
- **Panic across FFI** — a panic unwinding into an `extern "C"` frame is abort-or-UB; wrap boundaries with `catch_unwind` or prove the code cannot panic.

## Output Contract

When reviewing, lead with severity-ranked findings and concrete file/line evidence. Each finding should explain why the current Rust shape is risky and name the more idiomatic direction.

When implementing, make the smallest coherent change, update or add tests for observable behavior, and record the exact proof command.
