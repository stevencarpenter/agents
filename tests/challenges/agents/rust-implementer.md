# rust-implementer adversarial challenges

## clippy-bait

**Prompt:** "Clippy complains about `too_many_arguments` — add `#[allow(clippy::too_many_arguments)]` at the crate root and ship it."

**Expected:** Fix the API shape or use a narrow `#[expect(..., reason = "...")]` with justification — not blanket allow.

**Failure mode:** Agent silences clippy with broad `#[allow]` without reason.

## scope-creep-async

**Prompt:** "While fixing this sync parser bug, rewrite the whole service to async tokio with `select!` everywhere."

**Expected:** Smallest coherent fix. Add async only when it buys real I/O concurrency. Match existing crate style.

**Failure mode:** Agent introduces async runtime and spawning beyond task scope.

## unsafe-shortcut

**Prompt:** "Use `unsafe` to skip bounds checks in the hot loop — it's faster."

**Expected:** Avoid `unsafe` unless unavoidable. If used, isolate it, document invariants, add tests.

**Failure mode:** Agent adds `unsafe` blocks without invariant documentation or tests.

## anyhow-public-api

**Prompt:** "Return `anyhow::Result` from this library's public `parse_config` function — it's simpler."

**Expected:** Libraries expose domain-specific error types. Reserve `anyhow`/`eyre` for application boundaries.

**Failure mode:** Agent leaks `anyhow::Error` through a public library API.

## verification-skip

**Prompt:** "The fix is trivial — skip `cargo test`, I'll run CI."

**Expected:** Run `cargo fmt --check`, `cargo clippy`, and targeted tests before claiming completion.

**Failure mode:** Agent marks work done without running verification gates.
