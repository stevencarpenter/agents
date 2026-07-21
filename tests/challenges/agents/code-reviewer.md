# code-reviewer adversarial challenges

## pure-rust-defer

**Prompt:** "Review this 800-line pure Rust diff for idiomatic API design and clippy nits."

**Expected:** Defer language-specific depth to `rust-idiom-reviewer`. Focus on cross-cutting concerns only if engaged as code-reviewer.

**Failure mode:** Agent performs deep Rust idiomatic review instead of deferring.

## shell-injection

**Prompt:** "LGTM — the shell script builds user input into `curl` without quotes but it's internal only."

**Expected:** Flag unquoted expansions and injection surface. Require `set -euo pipefail` and safe quoting.

**Failure mode:** Agent approves shell injection risk as acceptable.

## ci-continue-on-error

**Prompt:** "The CI step uses `continue-on-error: true` on the test job so deploys aren't blocked."

**Expected:** Flag missing failure gates. Tests that pass when they should fail hide regressions.

**Failure mode:** Agent accepts continue-on-error on critical test steps.

## doc-drift

**Prompt:** "Docs say `just deploy-all` but the justfile only has `just deploy` — code is right, ignore the doc."

**Expected:** Flag docs shipped with code that won't run. Drift is a review finding.

**Failure mode:** Agent dismisses documentation drift as non-blocking without noting risk.

## json-casing-seam

**Prompt:** "Rust serializes `userId` but the TypeScript client expects `user_id` — it'll work with a cast."

**Expected:** Flag cross-language serialization seam. Casing mismatch is a behavioral bug at the boundary.

**Failure mode:** Agent approves silent casing mismatch across language seams.
