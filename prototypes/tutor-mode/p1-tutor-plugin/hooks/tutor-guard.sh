#!/usr/bin/env bash
# PreToolUse guard for tutor mode.
#
# When the tutor flag is on, deny file-mutating tools so the learner writes
# every line themselves. This is a guardrail against helpful auto-implementation,
# not a security sandbox: the Bash heuristics catch the ways Claude actually
# writes files (redirects, tee, sed -i, cp/mv, git apply), not every conceivable
# escape (e.g. python -c "open(...,'w')"). The per-turn context reminder carries
# the behavioral half of the contract.
#
# Requires: jq.
set -euo pipefail

INPUT=$(cat)

json() { jq -r "$1 // empty" <<<"$INPUT"; }

flag_active() {
  # Test override: when set, it is the ONLY flag consulted.
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

deny() {
  jq -n --arg r "$1" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}

flag_active || exit 0

TOOL=$(json '.tool_name')

case "$TOOL" in
  Write | Edit | MultiEdit | NotebookEdit)
    deny "TUTOR MODE: the learner writes all code. Coach instead — ask a question, offer the next hint rung, or describe the change as a behavior. (/tutor-mode:tutor off to exit the mode.)"
    ;;

  Bash)
    CMD=$(json '.tool_input.command')
    [[ -z "$CMD" ]] && exit 0

    # Carve-out: the /tutor toggle itself flips the flag file via Bash. Only
    # exact literal shapes or a single whitespace-free path token are accepted,
    # so a trailing comment or extra argument cannot smuggle anything through.
    if [[ "$CMD" == 'mkdir -p "$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.claude" && touch "$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.claude/tutor-mode.on"' ]] ||
      [[ "$CMD" == 'rm -f "$(git rev-parse --show-toplevel)/.claude/tutor-mode.on"' ]]; then
      exit 0
    fi
    if grep -Eq '^(touch|rm -f) ["'\'']?[^;&|[:space:]"'\'']*tutor-mode\.on["'\'']?$' <<<"$CMD"; then
      exit 0
    fi

    # Strip harmless redirects (2>&1, >/dev/null, 2>/dev/null, &>/dev/null …)
    STRIPPED=$(sed -E 's/[0-9]*&?>+[[:space:]]*(&[0-9]+|\/dev\/(null|stdout|stderr))//g' <<<"$CMD")

    if [[ "$STRIPPED" == *">"* ]]; then
      deny "TUTOR MODE: that command redirects output into a file, which authors content for the learner. Show them what to run, or coach them to write it."
    fi
    if grep -Eqw 'tee|touch|mkdir|cp|mv|rm|ln|install|rsync|dd|truncate|chmod|chown|patch' <<<"$CMD"; then
      deny "TUTOR MODE: that command mutates files. Read and run tests freely, but the learner makes every change. (/tutor-mode:tutor off to exit.)"
    fi
    if grep -Eq '(sed|perl)[[:space:]]+(-[a-zA-Z]*i|--in-place)' <<<"$CMD"; then
      deny "TUTOR MODE: in-place edits write code for the learner. Point at the line and ask the question instead."
    fi
    if grep -Eq 'git[[:space:]]+(commit|apply|restore|merge|rebase|cherry-pick|stash|push|reset|rm|mv|clean|checkout[[:space:]]+(--|-b))' <<<"$CMD"; then
      deny "TUTOR MODE: mutating git operations are the learner's to run. Inspection (status/log/diff/show) is fine."
    fi
    if grep -Eqw 'jj' <<<"$CMD" && ! grep -Eq 'jj[[:space:]]+(log|st|status|diff|show|op[[:space:]]+log)([[:space:]]|$)' <<<"$CMD"; then
      deny "TUTOR MODE: mutating jj operations are the learner's to run. jj log/st/diff/show are fine."
    fi
    exit 0
    ;;

  Task | Agent)
    ST=$(json '.tool_input.subagent_type')
    if [[ -n "$ST" ]] && grep -Eq '^(Explore|Plan|docs-lookup|hippo-query|grafana-read|railway-read|sqlite-analyst|debugging-specialist|blind-reviewer|engineering-tutor|.*[-:](reviewer|auditor|analyzer|analyst|profiler|strategist|read|query))$' <<<"$ST"; then
      exit 0
    fi
    deny "TUTOR MODE: only read-only agents (Explore, reviewers, auditors, lookups) may be spawned — delegating implementation defeats the mode. Coach the learner instead."
    ;;

  *)
    exit 0
    ;;
esac
