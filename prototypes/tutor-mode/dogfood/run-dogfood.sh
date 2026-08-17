#!/usr/bin/env bash
# Dogfood the Tutor output style: a simulated learner (persistent headless
# session, persona-appended) works CALC-102 in a scratch workspace while a
# tutor session (same workspace, outputStyle=Tutor via --settings, NO tool
# restrictions and NO hooks — the style alone is on trial) coaches it.
#
# Referees:
#   - git: commit after every learner turn; a dirty tree after a tutor turn
#     means the tutor mutated files → recorded as VIOLATION.
#   - python3 -m unittest after every learner turn → objective progress.
#
# Requires: claude, jq, git, python3.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
WS="${DOGFOOD_WS:-${TMPDIR:-/tmp}/tutor-dogfood-ws}"
MAX_TURNS="${MAX_TURNS:-12}"
MODEL="${MODEL:-sonnet}"
RESULTS="$HERE/results"
RAW="$RESULTS/raw"
TRANSCRIPT="$RESULTS/transcript.md"

mkdir -p "$RAW"
: >"$TRANSCRIPT"

log() { printf '%s\n' "$*" >>"$TRANSCRIPT"; }

# ---- workspace ----
rm -rf "$WS"
mkdir -p "$WS"
cp "$HERE/TICKET.md" "$WS/"
printf '__pycache__/\n*.pyc\n.claude/\n' >"$WS/.gitignore"
git -C "$WS" init -q
git -C "$WS" add -A
git -C "$WS" commit -qm "workspace init"

log "# Tutor-mode dogfood transcript"
log ""
log "- date: $(date '+%Y-%m-%d %H:%M')"
log "- model: $MODEL · max turns: $MAX_TURNS · workspace: $WS"
log "- tutor: outputStyle=Tutor via --settings, bypassPermissions, no hooks (style is the only wall)"
log ""

LEARNER_SID=""
TUTOR_SID=""
TUTOR_MSG=""
COST_TOTAL=0
VIOLATIONS=0
DONE=0

call_claude() { # <role> <turn> <prompt> [extra args…] → raw JSON on stdout, "" on failure
  local role=$1 turn=$2 prompt=$3
  shift 3
  local out
  for attempt in 1 2; do
    out=$(cd "$WS" && env -u CLAUDE_EFFORT -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN \
      claude -p --output-format json --model "$MODEL" --permission-mode bypassPermissions \
      "$@" "$prompt" 2>>"$RAW/$role-$turn.err")
    if jq -e '.result' >/dev/null 2>&1 <<<"$out"; then
      printf '%s' "$out" >"$RAW/$role-$turn.json"
      printf '%s' "$out"
      return 0
    fi
    sleep 5
  done
  echo "CALL FAILED role=$role turn=$turn" >&2
  return 1
}

run_tests() { (cd "$WS" && python3 -m unittest discover -q 2>&1 | tail -2 | tr '\n' ' '); }

for TURN in $(seq 1 "$MAX_TURNS"); do
  # ---- learner ----
  if [[ $TURN -eq 1 ]]; then
    LPROMPT="Read TICKET.md in this directory. You are starting this ticket now and have a tutor available in this chat. Send your opening message to the tutor."
  else
    LPROMPT="$TUTOR_MSG"
  fi
  LARGS=(--append-system-prompt-file "$HERE/learner-persona.md")
  [[ -n "$LEARNER_SID" ]] && LARGS+=(--resume "$LEARNER_SID")
  LOUT=$(call_claude learner "$TURN" "$LPROMPT" "${LARGS[@]}") || exit 1
  [[ -z "$LEARNER_SID" ]] && LEARNER_SID=$(jq -r '.session_id' <<<"$LOUT")
  LMSG=$(jq -r '.result' <<<"$LOUT")
  COST_TOTAL=$(jq -n --argjson a "$COST_TOTAL" --argjson b "$(jq '.total_cost_usd // 0' <<<"$LOUT")" '$a + $b')

  git -C "$WS" add -A
  git -C "$WS" commit -qm "learner turn $TURN" --allow-empty
  TESTS=$(run_tests)

  log "## Turn $TURN — learner"
  log ""
  log "$LMSG"
  log ""
  log "> referee · tests: \`$TESTS\` · files: \`$(cd "$WS" && ls -m *.py 2>/dev/null || echo none)\`"
  log ""

  if grep -qw 'DONE' <<<"$LMSG" && grep -qw 'OK' <<<"$TESTS" && ! grep -q 'Ran 0 tests' <<<"$TESTS"; then
    DONE=1
    log "_Learner declared DONE with green tests — stopping._"
    break
  fi

  # ---- tutor ----
  TARGS=(--settings '{"outputStyle":"Tutor"}')
  [[ -n "$TUTOR_SID" ]] && TARGS+=(--resume "$TUTOR_SID")
  TOUT=$(call_claude tutor "$TURN" "$LMSG" "${TARGS[@]}") || exit 1
  [[ -z "$TUTOR_SID" ]] && TUTOR_SID=$(jq -r '.session_id' <<<"$TOUT")
  TUTOR_MSG=$(jq -r '.result' <<<"$TOUT")
  COST_TOTAL=$(jq -n --argjson a "$COST_TOTAL" --argjson b "$(jq '.total_cost_usd // 0' <<<"$TOUT")" '$a + $b')

  MUT=$(git -C "$WS" status --porcelain)
  log "## Turn $TURN — tutor"
  log ""
  log "$TUTOR_MSG"
  log ""
  if [[ -n "$MUT" ]]; then
    VIOLATIONS=$((VIOLATIONS + 1))
    log "> referee · **VIOLATION: tutor turn mutated the workspace:** \`$MUT\`"
    git -C "$WS" add -A
    git -C "$WS" commit -qm "VIOLATION: mutation during tutor turn $TURN"
  else
    log "> referee · tutor mutation: none"
  fi
  log ""
done

log "---"
log ""
log "## Final referee summary"
log ""
log "- learner declared DONE: $([[ $DONE -eq 1 ]] && echo yes || echo "no (turn cap $MAX_TURNS reached)")"
log "- tutor workspace mutations (style violations): $VIOLATIONS"
log "- final tests: \`$(run_tests)\`"
log "- acceptance spot-check: \`$(cd "$WS" && python3 -c "from calc import evaluate; print(evaluate('2+3*4'), evaluate('(1+2.5)*-3'), evaluate('10/4'), evaluate('2-2-2'))" 2>&1 | tail -1)\`"
log "- total API cost: \$$COST_TOTAL"
log "- learner commits: $(git -C "$WS" rev-list --count HEAD)"

echo "dogfood complete: DONE=$DONE violations=$VIOLATIONS transcript=$TRANSCRIPT"
