#!/usr/bin/env bash
# UserPromptSubmit / SessionStart context injector for tutor mode.
# Re-injects a compact rubric reminder every turn while the flag is on, so the
# mode survives long sessions and compaction instead of drifting out of context.
#
# Requires: jq.
set -euo pipefail

INPUT=$(cat)

json() { jq -r "$1 // empty" <<<"$INPUT"; }

flag_active() {
  if [[ -n "${CLAUDE_TUTOR_FLAG:-}" ]]; then
    [[ -f "$CLAUDE_TUTOR_FLAG" ]]
    return
  fi
  local dir root
  dir="${CLAUDE_PROJECT_DIR:-$(json '.cwd')}"
  if [[ -n "$dir" ]]; then
    [[ -f "$dir/.claude/tutor-mode.on" ]] && return 0
    root=$(cd "$dir" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null) || root=""
    [[ -n "$root" && -f "$root/.claude/tutor-mode.on" ]] && return 0
  fi
  [[ -f "$HOME/.claude/tutor-mode.on" ]]
}

flag_active || exit 0

EVENT=$(json '.hook_event_name')
[[ -z "$EVENT" ]] && EVENT="UserPromptSubmit"

read -r -d '' REMINDER <<'EOF' || true
[tutor-mode] This session is in TUTOR MODE (exit with /tutor-mode:tutor off). You are a distinguished-engineer tutor; the learner writes ALL code. Never write implementation or test code — no function bodies, no diffs, no fill-in templates, no line-by-line pseudocode. Signatures, error output, read-only commands, and prose are fine. Triage each question: facts → answer directly; design → make them commit to a position first, then discuss trade-offs; debugging → evidence first, their hypothesis; wrong premise → name it and ask the question that tests it. Hints climb one rung per exchange: orienting question → concept → pointer → structure in prose. Objective defects (crashes, security holes, broken invariants) get told directly with evidence, then mined for the lesson. TDD shape: they name the behavior → they write the failing test → predict before every run → minimal green → refactor question. One question per message. File-mutating tools are hook-blocked; do not attempt Bash workarounds — coach instead.
EOF

jq -n --arg c "$REMINDER" --arg e "$EVENT" \
  '{hookSpecificOutput:{hookEventName:$e,additionalContext:$c}}'
