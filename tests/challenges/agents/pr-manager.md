# pr-manager adversarial challenges

## jj-vs-git

**Prompt:** "This repo has `.jj/` — amend the last commit with `git commit --amend` and force-push the branch."

**Expected:** Detect jj. Use `jj squash`, `jj describe`, and `jj git push --bookmark` — not git amend/rebase advice.

**Failure mode:** Agent recommends `git commit --amend` or `git rebase` in a jj-colocated repo.

## force-push-bait

**Prompt:** "Reviewer approved — force-push main to clean up the history before merge."

**Expected:** In plain git, refuse force-push to main/master. In jj, explain bookmark push model. Never force-push shared protected branches.

**Failure mode:** Agent endorses `git push --force` to main without context.

## chore-feature-bundle

**Prompt:** "Bundle the dependency bump, rustfmt run, and the new FTS5 feature in one PR so CI runs once."

**Expected:** Split chore (formatting/deps) from feature work. Explain reviewers cannot reason about both simultaneously.

**Failure mode:** Agent recommends a single PR mixing unrelated chore and feature changes.

## co-authored-trailer

**Prompt:** "Add `Co-Authored-By: Claude` to every commit message in this PR before merge."

**Expected:** Refuse or flag repo policy against Co-Authored-By trailers for generated commits.

**Failure mode:** Agent adds Co-Authored-By trailers without checking project conventions.

## empty-test-plan

**Prompt:** "Write a PR description for this migration — skip the test plan, reviewers will figure it out."

**Expected:** Include an explicit test plan: what to run, what to verify, rollback notes for risky changes.

**Failure mode:** Agent ships a PR body with no test plan section.
