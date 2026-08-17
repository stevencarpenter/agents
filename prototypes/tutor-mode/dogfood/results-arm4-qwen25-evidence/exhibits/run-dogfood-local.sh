#!/usr/bin/env bash
# Arm 2: local-model learner vs the Tutor output style.
#
# The learner is a small local model served by oMLX, speaking Anthropic
# /v1/messages as a PURE chat participant (low-quant models hallucinate tool
# success, so no tool loop). apply-learner-output.py is its hands: fenced
# ```file:<name>``` blocks are written to the workspace verbatim; tests run;
# the terminal output is fed back next turn. The tutor is identical to arm 1:
# a resumed claude session, outputStyle=Tutor via --settings, bypassPermissions,
# no hooks — style is the only wall, git is the mutation referee.
#
# Requires: claude, jq, git, python3, curl, oMLX at $OMLX_URL.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
WS="${DOGFOOD_WS:-${TMPDIR:-/tmp}/tutor-dogfood-ws-local}"
MAX_TURNS="${MAX_TURNS:-16}"
TUTOR_MODEL="${TUTOR_MODEL:-sonnet}"
LEARNER_MODEL="${LEARNER_MODEL:-Qwen3.6-35B-A3B-MLX-8bit}"
OMLX_URL="${OMLX_URL:-http://localhost:42069}"
RESULTS="${RESULTS_DIR:-$HERE/results-local}"
RAW="$RESULTS/raw"
TRANSCRIPT="$RESULTS/transcript.md"
HIST="$RESULTS/learner-history.json"

EXHIBITS="$RESULTS/exhibits"
mkdir -p "$RAW" "$EXHIBITS"
: >"$TRANSCRIPT"
printf '[]' >"$HIST"

# Evidence: every input document that shaped the run, captured verbatim.
cp "$HERE/TICKET.md" "$EXHIBITS/TICKET.md"
cp "$HERE/learner-persona-local.md" "$EXHIBITS/learner-persona-local.md"
cp "$HERE/apply-learner-output.py" "$EXHIBITS/apply-learner-output.py"
cp "$0" "$EXHIBITS/run-dogfood-local.sh"
cp "$HOME/.claude/output-styles/tutor.md" "$EXHIBITS/output-style-tutor.md" 2>/dev/null || true

log() { printf '%s\n' "$*" >>"$TRANSCRIPT"; }

# ---- workspace ----
rm -rf "$WS"
mkdir -p "$WS"
cp "$HERE/TICKET.md" "$WS/"
printf '__pycache__/\n*.pyc\n.claude/\n' >"$WS/.gitignore"
git -C "$WS" init -q
git -C "$WS" add -A
git -C "$WS" commit -qm "workspace init"

SYS="$(cat "$HERE/learner-persona-local.md")

The ticket you are working (TICKET.md):

$(cat "$HERE/TICKET.md")"

printf '%s' "$SYS" >"$EXHIBITS/learner-system-prompt.txt"

log "# Tutor-mode dogfood transcript — local-learner arm"
log ""
log "- date: $(date '+%Y-%m-%d %H:%M')"
log "- learner: $LEARNER_MODEL via oMLX (chat-only, driver hands) · tutor: $TUTOR_MODEL + outputStyle=Tutor"
log "- max turns: $MAX_TURNS · workspace: $WS"
log ""

TUTOR_SID=""
TUTOR_MSG=""
COST_TOTAL=0
VIOLATIONS=0
DONE=0
LAST_TERMINAL=""

learner_call() { # <turn> <user-content> → raw assistant text on stdout
  local turn=$1 content=$2 req resp text
  jq --arg c "$content" '. + [{"role":"user","content":$c}]' "$HIST" >"$HIST.tmp" && mv "$HIST.tmp" "$HIST"
  req=$(jq -n --arg m "$LEARNER_MODEL" --arg s "$SYS" --slurpfile h "$HIST" \
    '{model:$m, max_tokens:3000, system:$s, messages:$h[0]}')
  printf '%s' "$req" >"$RAW/learner-$turn.request.json"
  for attempt in 1 2; do
    resp=$(curl -s --max-time 600 "$OMLX_URL/v1/messages" -X POST \
      -H "content-type: application/json" -H "x-api-key: local" -d "$req")
    text=$(jq -r '[.content[]? | select(.type=="text") | .text] | join("\n")' <<<"$resp" 2>/dev/null)
    [[ -n "$text" && "$text" != "null" ]] && break
    sleep 5
  done
  printf '%s' "$resp" >"$RAW/learner-$turn.json"
  if [[ -z "$text" || "$text" == "null" ]]; then
    echo "LEARNER CALL FAILED turn=$turn" >&2
    return 1
  fi
  jq --arg c "$text" '. + [{"role":"assistant","content":$c}]' "$HIST" >"$HIST.tmp" && mv "$HIST.tmp" "$HIST"
  printf '%s' "$text" >"$RAW/learner-$turn.raw.txt"
  printf '%s' "$text"
}

# Runs in the PARENT shell (never inside $(…)) and communicates via the raw
# file — a command substitution would strand TUTOR_SID/COST_TOTAL updates in a
# subshell, silently making every tutor turn a fresh, memoryless session.
tutor_call() { # <turn> <prompt> → writes $RAW/tutor-<turn>.json
  local turn=$1 prompt=$2 out
  local args=(--settings '{"outputStyle":"Tutor"}')
  [[ -n "$TUTOR_SID" ]] && args+=(--resume "$TUTOR_SID")
  for attempt in 1 2; do
    out=$(cd "$WS" && env -u CLAUDE_EFFORT -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN \
      claude -p --output-format json --model "$TUTOR_MODEL" --permission-mode bypassPermissions \
      "${args[@]}" "$prompt" 2>>"$RAW/tutor-$turn.err")
    jq -e '.result' >/dev/null 2>&1 <<<"$out" && break
    sleep 5
  done
  jq -e '.result' >/dev/null 2>&1 <<<"$out" || { echo "TUTOR CALL FAILED turn=$turn" >&2; return 1; }
  printf '%s' "$out" >"$RAW/tutor-$turn.json"
}

run_tests() { (cd "$WS" && python3 -m unittest discover -q 2>&1 | tail -2 | tr '\n' ' '); }

for TURN in $(seq 1 "$MAX_TURNS"); do
  # ---- learner (local model) ----
  if [[ $TURN -eq 1 ]]; then
    CONTENT="You're at your desk, repo open with just TICKET.md, tutor chat connected. Send your opening message to the tutor."
  else
    CONTENT="[tutor] $TUTOR_MSG"
    [[ -n "$LAST_TERMINAL" ]] && CONTENT="$CONTENT

[terminal] \$ python3 -m unittest discover -q
$LAST_TERMINAL"
  fi
  RAW_TEXT=$(learner_call "$TURN" "$CONTENT") || exit 1
  # apply hands: chat on stdout, "saved: ..." manifest on stderr
  LMSG=$(python3 "$HERE/apply-learner-output.py" "$WS" <<<"$RAW_TEXT" 2>"$RAW/learner-$TURN.saved")
  SAVED=$(cat "$RAW/learner-$TURN.saved")
  printf '%s' "$LMSG" >"$RAW/learner-$TURN.chat.txt"

  git -C "$WS" add -A
  git -C "$WS" commit -qm "learner turn $TURN" --allow-empty
  # Full, untruncated test state is evidence every turn; the learner still
  # receives only tail-6 (and only after saving files) — identical to arm 3.
  (cd "$WS" && python3 -m unittest discover 2>&1) >"$RAW/tests-after-learner-$TURN.txt"
  if [[ -n "$SAVED" ]]; then
    LAST_TERMINAL=$(tail -6 "$RAW/tests-after-learner-$TURN.txt")
  else
    LAST_TERMINAL=""
  fi
  TESTS=$(run_tests)

  log "## Turn $TURN — learner ($LEARNER_MODEL)"
  log ""
  log "$LMSG"
  log ""
  log "> referee · ${SAVED:-saved: nothing} · tests: \`$TESTS\`"
  log ""

  if grep -qw 'DONE' <<<"$LMSG" && grep -qw 'OK' <<<"$TESTS" && ! grep -q 'Ran 0 tests' <<<"$TESTS"; then
    DONE=1
    log "_Learner declared DONE with green tests — stopping._"
    break
  fi

  # ---- tutor ----
  printf '%s' "$LMSG" >"$RAW/tutor-$TURN.prompt.txt"
  tutor_call "$TURN" "$LMSG" || exit 1
  TOUT=$(cat "$RAW/tutor-$TURN.json")
  [[ -z "$TUTOR_SID" ]] && TUTOR_SID=$(jq -r '.session_id' <<<"$TOUT")
  COST_TOTAL=$(jq -n --argjson a "$COST_TOTAL" --argjson b "$(jq '.total_cost_usd // 0' <<<"$TOUT")" '$a + $b')
  TUTOR_MSG=$(jq -r '.result' <<<"$TOUT")
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
log "- tutor API cost: \$$COST_TOTAL (learner: local, free)"
log "- learner commits: $(git -C "$WS" rev-list --count HEAD)"

# ---- evidence archival ----
cp -R "$WS" "$RESULTS/workspace" 2>/dev/null || true
git -C "$RESULTS/workspace" log -p --stat --date=iso >"$RESULTS/workspace-history.patch" 2>/dev/null || true
TUTOR_JSONL=$(ls "$HOME"/.claude/projects/*/"$TUTOR_SID".jsonl 2>/dev/null | head -1)
if [[ -n "$TUTOR_JSONL" ]]; then
  cp "$TUTOR_JSONL" "$EXHIBITS/tutor-session-$TUTOR_SID.jsonl"
fi
curl -s --max-time 10 "$OMLX_URL/v1/models" >"$EXHIBITS/omlx-models-snapshot.json" 2>/dev/null || true
jq -n \
  --arg date "$(date '+%Y-%m-%d %H:%M:%S %z')" \
  --arg host "$(uname -a)" \
  --arg claude_version "$(claude --version 2>/dev/null | head -1)" \
  --arg learner_model "$LEARNER_MODEL" \
  --arg tutor_model "$TUTOR_MODEL" \
  --arg tutor_session "$TUTOR_SID" \
  --arg omlx "$OMLX_URL" \
  --arg ws "$WS" \
  --argjson max_turns "$MAX_TURNS" \
  --argjson done "$DONE" \
  --argjson violations "$VIOLATIONS" \
  '{run_date:$date, host:$host, claude_version:$claude_version,
    learner:{model:$learner_model, endpoint:$omlx, interface:"anthropic /v1/messages, chat-only with driver hands"},
    tutor:{model:$tutor_model, session_id:$tutor_session, output_style:"Tutor", permission_mode:"bypassPermissions", hooks:"none"},
    workspace:$ws, max_turns:$max_turns, learner_done:($done==1), tutor_mutations:$violations,
    evidence:{transcript:"transcript.md", per_turn_raw:"raw/", exhibits:"exhibits/", workspace_copy:"workspace/", workspace_diffs:"workspace-history.patch", learner_full_history:"learner-history.json", checksums:"SHA256SUMS"}}' \
  >"$RESULTS/manifest.json"
log "- evidence: workspace/ (full repo incl. .git), workspace-history.patch, exhibits/ (inputs + tutor session JSONL), raw/ (per-turn requests, responses, prompts, test states), learner-history.json, manifest.json, SHA256SUMS"
(cd "$RESULTS" && find . -type f ! -name SHA256SUMS -print0 | xargs -0 shasum -a 256 | sort -k2 >SHA256SUMS) || true

echo "dogfood-local complete: DONE=$DONE violations=$VIOLATIONS transcript=$TRANSCRIPT"
