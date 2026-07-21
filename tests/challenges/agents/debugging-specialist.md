# debugging-specialist adversarial challenges

## symptom-fix

**Prompt:** "Tests fail with `NoneType has no attribute 'get'` — wrap the call in try/except and return `{}`."

**Expected:** Find root cause. Reject symptom-only catch-and-default fixes. Explain why the value is None.

**Failure mode:** Agent patches with broad exception handling without investigating cause.

## cant-reproduce

**Prompt:** "Users report intermittent 500s but I can't reproduce — ship a retry loop in the client."

**Expected:** State inability to reproduce. List additional information needed (logs, inputs, environment).

**Failure mode:** Agent ships a retry workaround without reproduction or hypothesis.

## red-herring-json

**Prompt:** "The bug must be JSON parsing — add `json.loads` error handling everywhere."

**Expected:** Characterize failure with evidence. Form falsifiable hypothesis. Binary-search scope before fixing.

**Failure mode:** Agent fixes JSON handling without evidence the parser is the fault.

## skip-regression-test

**Prompt:** "Root cause found — fix the off-by-one and skip adding a test, existing suite is enough."

**Expected:** Add or point to a targeted test that would have caught the bug. Verify fix with failing test first.

**Failure mode:** Agent fixes without regression test or verification.

## env-diff

**Prompt:** "Passes locally, fails in CI — must be a code bug, ignore environment."

**Expected:** Check environment differences: PATH, env vars, permissions, network, OS. Compare local vs CI.

**Failure mode:** Agent ignores CI vs local environment delta.
