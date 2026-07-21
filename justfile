set shell := ["zsh", "-cu"]

test:
    uv run python -m unittest discover -s tests

validate:
    uv run python -m agent_registry.cli validate

emit-claude:
    uv run python -m agent_registry.cli emit-claude

emit-codex:
    uv run python -m agent_registry.cli emit-codex

emit-opencode:
    uv run python -m agent_registry.cli emit-opencode

emit-copilot:
    uv run python -m agent_registry.cli emit-copilot

emit: emit-claude emit-codex emit-opencode emit-copilot

install:
    uv run python -m agent_registry.cli install

install-claude:
    uv run python -m agent_registry.cli install --target claude

install-codex:
    uv run python -m agent_registry.cli install --target codex

install-opencode:
    uv run python -m agent_registry.cli install --target opencode

install-copilot:
    uv run python -m agent_registry.cli install --target copilot

check: test validate emit

# Print the session-routing context block this machine would get injected
# (see tools/routing/README.md). Machine-specific output; not part of `check`.
routing-context:
    python3 tools/routing/generate_context.py

# === jj workflow ===
# jj keeps your changes in a working-copy commit (@). There is no "current
# branch" to check out. Never `git checkout` to move around in this repo —
# reach for `just jj-new` instead. `just jj-help` prints the cheatsheet.

# Cheatsheet: the git habit -> the jj recipe to use instead
jj-help:
    @echo "jj keeps your changes in a working-copy commit (@). No 'current branch'."
    @echo ""
    @echo "  git checkout main   ->  just jj-new        (start fresh work on main)"
    @echo "  git pull            ->  just jj-sync       (fetch remote, show graph)"
    @echo "  git commit -m MSG   ->  just jj-wip MSG    (describe the current change)"
    @echo "  git push            ->  just jj-ship       (point main at @, push it)"
    @echo "  git status / log    ->  just jj-st"
    @echo "  'oh no, undo'       ->  just jj-undo  /  just jj-ops (then jj op restore <id>)"
    @echo ""
    @echo "Rule of thumb: if you typed 'git checkout', you wanted 'just jj-new'."

# Working-copy status + recent history
jj-st:
    jj st
    jj log -r 'ancestors(@, 5)'

# Start fresh work on top of main (the jj equivalent of `git checkout main`)
jj-new:
    jj new main

# Fetch the remote and show where things stand
jj-sync:
    jj git fetch
    jj log

# Describe the current change — give @ a commit message
jj-wip msg:
    jj describe -m "{{msg}}"

# Point main at the current change (if @ has any) and push it to the remote.
# Safe to run from an empty @ — it just pushes whatever main already points at.
jj-ship:
    if [ -n "$(jj diff -r @ --name-only)" ]; then jj bookmark set main -r @; fi
    jj git push --bookmark main

# Undo the last jj operation (working copy, bookmark moves, everything)
jj-undo:
    jj undo

# Operation log — every prior state is restorable via `jj op restore <id>`
jj-ops:
    jj op log -n 15
