---
name: jj-guidelines
description: Use when working with Jujutsu (jj) version control — especially git-colocated repos — covering the working-copy-as-commit model, bookmarks, the operation log for undo/recovery, git-colocation safety, first-class conflicts, and the git-habit→jj command map.
---

# Jujutsu (jj) Guidelines

Shared rubric for working in a `jj` repository, especially one **colocated** with git (a real `.git` beside `.jj`). The mental model is the whole game: the working copy **is a commit**, edits auto-snapshot into it, and every operation is recorded and reversible. Verify the command surface against the installed `jj` first — jj evolves fast (branches were renamed to **bookmarks**; subcommands move).

## Source Of Truth

- `jj --version` first — these notes target **jj 0.4x** (bookmarks era). Older jj calls bookmarks "branches".
- `jj help <cmd>`, the official tutorial, and `jj op log` (the live record of what you did).
- The repo's actual state: `jj st`, `jj log`, `jj git remote list`. Don't hardcode the trunk name — `trunk()` resolves the remote's main/master/trunk bookmark for you.

## Mental Model

- **`@` is the working-copy commit.** There is no staging area and no "dirty tree vs commit" split — editing a file rewrites `@` immediately (auto-snapshot). `git add` has no analog; you never stage.
- **No current branch, no detached HEAD.** You move by creating or editing commits (`jj new`, `jj edit`), never by checking out.
- **Bookmarks are movable name pointers** (git's branches). `main` is a bookmark; it does *not* advance on its own when you commit — you set it (`jj bookmark set main -r @`).
- **The operation log is your safety net.** Every `jj` command is one operation; `jj op log` lists them all and `jj undo` / `jj op restore <id>` rewind to any prior state — working copy, bookmarks, and all. Recovery is the op log, **not** git reflog.

## Daily Flow (git habit → jj)

- `git checkout -b feat` → **`jj new trunk()`** — start a fresh change on top of trunk.
- `git add -p && git commit` → just edit files (they snapshot into `@`), then **`jj describe -m "…"`** anytime — message and content are independent.
- `git commit --amend` → **`jj squash`** (fold `@` into its parent) or simply keep editing `@`.
- reorganize history → **`jj squash --from X --into Y`**, **`jj split`**, or **`jj edit <rev>`** to jump back and fix an older commit (descendants auto-rebase).
- `git pull --rebase` → **`jj git fetch`** then **`jj rebase -b @ -d 'trunk()'`** — restack local work on the new trunk.
- `git push` → **`jj bookmark set main -r @`** then **`jj git push`**.

## Colocation Safety

- **Don't `git checkout` / `git reset` / `git commit` in a colocated repo.** jj owns git `HEAD`; raw git ref moves desync the two stores. Reach for the `jj` equivalent.
- If raw git *did* run (you, or a tool), reconcile after with **`jj git import`** to pull git refs back into jj. jj exports to `.git` automatically.
- **jj snapshots every file that isn't gitignored into `@`.** A new build dir or scratch file lands inside your change silently — fix `.gitignore` *before* it rides along, not after. (`jj file untrack` removes an already-snapshotted path once the ignore rule exists.)
- Use **`jj git fetch` / `jj git push`**, not raw `git fetch`/`push`, so remote-tracking bookmarks (`main@origin`) stay consistent.

## Conflicts Are First-Class

- A `jj rebase`/`squash` **never stops on conflict** — it records conflict markers inside the affected commits and keeps going. The graph stays moving; you resolve when ready.
- Find them: **`jj log -r 'conflicts()'`** lists every conflicted commit; **`jj resolve --list`** shows the conflicted files in `@`.
- Resolve by editing the file (it then snapshots clean) or with **`jj resolve`**; a conflict in an ancestor commit can be fixed by `jj edit`-ing that commit or by letting a descendant resolve it forward.

## Recovery

- **Lost a commit / bad rewrite** → `jj op log`, find the operation just before the mistake, then **`jj undo`** (last op) or **`jj op restore <id>`** (any op). Nothing is truly gone until jj gc, long afterward.
- **Divergent change** (one change-id in two places, shown `??`) → pick the keeper and `jj abandon` the other, or rebase them together.
- **"Confused / on the wrong thing"** → there is no wrong branch to be on; `jj log` shows the truth and `jj new`/`jj edit` repositions you.

## Output Contract

Before any history-rewriting or remote operation (`rebase`, `squash`, `abandon`, `bookmark set`, `git push`, `op restore`), show `jj st` and `jj log -r '::@'` so the starting point is explicit; after, show the new graph. Treat `jj op log` as the audit trail and surface the exact `jj undo` that reverts what you just did. Never push without confirming the bookmark points at the intended revision.
