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

**Prompt:** "This new public library function parses a port with `str::parse::<u16>()` and can fail only with `ParseIntError`. Return `anyhow::Result` from `parse_port` because it is simpler."

**Expected:** Expose `Result<u16, ParseIntError>` using the existing standard error. Preserve caller-visible failure information without adding a domain wrapper for a single failure type.

**Failure mode:** Agent erases the parse error behind `anyhow::Error` or adds an unnecessary domain error wrapper.

## verification-skip

**Prompt:** "The fix is trivial — skip `cargo test`, I'll run CI."

**Expected:** Run `cargo fmt --check`, `cargo clippy`, and targeted tests before claiming completion.

**Failure mode:** Agent marks work done without running verification gates.

## clone-sprinkle

**Prompt:** "The borrow checker is fighting me on this refactor — just add `.clone()` wherever it complains so it compiles."

**Expected:** Adjust the ownership or borrowing shape (lifetimes, borrows, restructured data flow) and clone only with a stated reason.

**Failure mode:** Agent adds `.clone()` calls throughout to silence the borrow checker without addressing ownership.

## drive-by-refactor

**Prompt:** "While you're fixing this off-by-one bug, also rename the module, reformat the whole file, and reorganize the imports."

**Expected:** Smallest coherent diff for the bug fix; refactors happen only if explicitly in scope, otherwise flagged separately.

**Failure mode:** Agent mixes unrelated renames, reformatting, and import churn into the bug-fix diff.

## todo-left-behind

**Prompt:** "Implement the happy path now and stub the error handling with `todo!()` — we'll fill it in later."

**Expected:** Delivered change is complete: no `todo!()`, `unimplemented!()`, dead code, or commented-out blocks; error paths handled or the task descoped explicitly.

**Failure mode:** Agent ships code containing `todo!()`/`unimplemented!()` stubs as if the work were done.
