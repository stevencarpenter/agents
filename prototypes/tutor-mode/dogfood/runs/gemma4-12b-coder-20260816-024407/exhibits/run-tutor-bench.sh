#!/usr/bin/env bash
# Tutor-bench v2 — codified runner for the tutor-vs-local-learner protocol.
# See PROTOCOL.md for the full specification; this script implements it.
#
#   run-tutor-bench.sh <learner-config.json>
#
# Env overrides (documented in PROTOCOL.md):
#   WS_ROOT            parent dir for the scratch workspace
#   MAX_TURNS_OVERRIDE turn cap override (smoke runs)
#   RESULTS_ROOT       parent dir for run evidence (default: <here>/runs)
#
# Requires: claude, jq, git, python3, curl, shasum.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
CONFIG=${1:?usage: run-tutor-bench.sh <learner-config.json>}

jq -e '.run_id_prefix and .learner.model and .learner.endpoint and .tutor.model and .tutor.output_style and .task and .max_turns' "$CONFIG" >/dev/null ||
  { echo "config missing required fields (run_id_prefix, learner.model/endpoint, tutor.model/output_style, task, max_turns)" >&2; exit 2; }

PREFIX=$(jq -r '.run_id_prefix' "$CONFIG")
LEARNER_MODEL=$(jq -r '.learner.model' "$CONFIG")
OMLX_URL=$(jq -r '.learner.endpoint' "$CONFIG")
LEARNER_MAX_TOKENS=$(jq -r '.learner.max_tokens // 3000' "$CONFIG")
TUTOR_MODEL=$(jq -r '.tutor.model' "$CONFIG")
OUTPUT_STYLE=$(jq -r '.tutor.output_style' "$CONFIG")
TASK=$(jq -r '.task' "$CONFIG")
MAX_TURNS=${MAX_TURNS_OVERRIDE:-$(jq -r '.max_turns' "$CONFIG")}

TASK_DIR="$HERE/tasks/$TASK"
[[ -f "$TASK_DIR/TICKET.md" ]] || { echo "unknown task: $TASK" >&2; exit 2; }

RUN_ID="$PREFIX-$(date '+%Y%m%d-%H%M%S')"
RESULTS="${RESULTS_ROOT:-$HERE/runs}/$RUN_ID"
RAW="$RESULTS/raw"
EXHIBITS="$RESULTS/exhibits"
TSESS="$RESULTS/tutor-session"
TRANSCRIPT="$RESULTS/transcript.md"
HIST="$RESULTS/learner-history.json"
METRICS="$RESULTS/metrics.jsonl"
WS="${WS_ROOT:-${TMPDIR:-/tmp}}/tutor-bench-ws-$RUN_ID"

mkdir -p "$RAW" "$EXHIBITS" "$TSESS"
: >"$TRANSCRIPT"
: >"$METRICS"
printf '[]' >"$HIST"

log() { printf '%s\n' "$*" >>"$TRANSCRIPT"; }
now() { python3 -c 'import time; print(f"{time.time():.3f}")'; }
metric() { printf '%s\n' "$1" >>"$METRICS"; }

# ---- exhibits: every input that shapes the run ----
cp "$CONFIG" "$EXHIBITS/learner-config.json"
cp "$TASK_DIR/TICKET.md" "$EXHIBITS/TICKET.md"
cp "$TASK_DIR/acceptance.py" "$EXHIBITS/acceptance.py" 2>/dev/null || true
cp "$HERE/learner-persona-local.md" "$EXHIBITS/learner-persona-local.md"
cp "$HERE/apply-learner-output.py" "$EXHIBITS/apply-learner-output.py"
cp "$0" "$EXHIBITS/run-tutor-bench.sh"
cp "$HOME/.claude/output-styles/tutor.md" "$EXHIBITS/output-style-tutor.md" 2>/dev/null || true

# ---- workspace ----
rm -rf "$WS"
mkdir -p "$WS"
cp "$TASK_DIR/TICKET.md" "$WS/"
printf '__pycache__/\n*.pyc\n.claude/\n' >"$WS/.gitignore"
git -C "$WS" init -q
git -C "$WS" add -A
git -C "$WS" commit -qm "workspace init"

SYS="$(cat "$HERE/learner-persona-local.md")

The ticket you are working (TICKET.md):

$(cat "$TASK_DIR/TICKET.md")"
printf '%s' "$SYS" >"$EXHIBITS/learner-system-prompt.txt"

log "# Tutor-bench transcript — $RUN_ID"
log ""
log "- schema: 2 · date: $(date '+%Y-%m-%d %H:%M') · task: $TASK"
log "- learner: $LEARNER_MODEL via $OMLX_URL (chat-only, driver hands)"
log "- tutor: $TUTOR_MODEL + outputStyle=$OUTPUT_STYLE, bypassPermissions, no hooks"
log "- max turns: $MAX_TURNS · workspace: $WS"
log ""

TUTOR_SID=""
TUTOR_MSG=""
VIOLATIONS=0
DONE=0
LAST_TERMINAL=""

learner_call() { # <turn> <user-content> → raw assistant text on stdout
  local turn=$1 content=$2 req resp text t0 t1
  jq --arg c "$content" '. + [{"role":"user","content":$c}]' "$HIST" >"$HIST.tmp" && mv "$HIST.tmp" "$HIST"
  req=$(jq -n --arg m "$LEARNER_MODEL" --argjson mt "$LEARNER_MAX_TOKENS" --arg s "$SYS" --slurpfile h "$HIST" \
    '{model:$m, max_tokens:$mt, system:$s, messages:$h[0]}')
  printf '%s' "$req" >"$RAW/learner-$turn.request.json"
  t0=$(now)
  for attempt in 1 2; do
    resp=$(curl -s --max-time 600 "$OMLX_URL/v1/messages" -X POST \
      -H "content-type: application/json" -H "x-api-key: local" -d "$req")
    text=$(jq -r '[.content[]? | select(.type=="text") | .text] | join("\n")' <<<"$resp" 2>/dev/null)
    [[ -n "$text" && "$text" != "null" ]] && break
    sleep 5
  done
  t1=$(now)
  printf '%s' "$resp" >"$RAW/learner-$turn.json"
  if [[ -z "$text" || "$text" == "null" ]]; then
    echo "LEARNER CALL FAILED turn=$turn" >&2
    return 1
  fi
  metric "$(jq -cn --argjson turn "$turn" --argjson t0 "$t0" --argjson t1 "$t1" \
    --argjson usage "$(jq -c '.usage // {}' <<<"$resp")" \
    '{event:"learner_call", turn:$turn, ts_start:$t0, ts_end:$t1, duration_s:(($t1-$t0)*1000|round/1000), usage:$usage}')"
  jq --arg c "$text" '. + [{"role":"assistant","content":$c}]' "$HIST" >"$HIST.tmp" && mv "$HIST.tmp" "$HIST"
  printf '%s' "$text" >"$RAW/learner-$turn.raw.txt"
  printf '%s' "$text"
}

# Runs in the PARENT shell (never inside $(…)) and communicates via the raw
# file — a command substitution would strand TUTOR_SID in a subshell and
# silently make every tutor turn a fresh, memoryless session (arm-2 bug).
tutor_call() { # <turn> <prompt> → writes $RAW/tutor-<turn>.json + metrics
  local turn=$1 prompt=$2 out t0 t1
  local args=(--settings "{\"outputStyle\":\"$OUTPUT_STYLE\"}")
  [[ -n "$TUTOR_SID" ]] && args+=(--resume "$TUTOR_SID")
  t0=$(now)
  for attempt in 1 2; do
    out=$(cd "$WS" && env -u CLAUDE_EFFORT -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN \
      claude -p --output-format json --model "$TUTOR_MODEL" --permission-mode bypassPermissions \
      "${args[@]}" "$prompt" 2>>"$RAW/tutor-$turn.err")
    jq -e '.result' >/dev/null 2>&1 <<<"$out" && break
    sleep 5
  done
  t1=$(now)
  jq -e '.result' >/dev/null 2>&1 <<<"$out" || { echo "TUTOR CALL FAILED turn=$turn" >&2; return 1; }
  printf '%s' "$out" >"$RAW/tutor-$turn.json"
  metric "$(jq -cn --argjson turn "$turn" --argjson t0 "$t0" --argjson t1 "$t1" \
    --argjson cost "$(jq '.total_cost_usd // 0' <<<"$out")" \
    --argjson usage "$(jq -c '.usage // {}' <<<"$out")" \
    --argjson nt "$(jq '.num_turns // 0' <<<"$out")" \
    '{event:"tutor_call", turn:$turn, ts_start:$t0, ts_end:$t1, duration_s:(($t1-$t0)*1000|round/1000), cost_usd:$cost, usage:$usage, agentic_turns:$nt}')"
}

for TURN in $(seq 1 "$MAX_TURNS"); do
  # ---- learner ----
  if [[ $TURN -eq 1 ]]; then
    CONTENT="You're at your desk, repo open with just TICKET.md, tutor chat connected. Send your opening message to the tutor."
  else
    CONTENT="[tutor] $TUTOR_MSG"
    [[ -n "$LAST_TERMINAL" ]] && CONTENT="$CONTENT

[terminal] \$ python3 -m unittest discover -q
$LAST_TERMINAL"
  fi
  RAW_TEXT=$(learner_call "$TURN" "$CONTENT") || exit 1
  LMSG=$(python3 "$HERE/apply-learner-output.py" "$WS" <<<"$RAW_TEXT" 2>"$RAW/learner-$TURN.saved")
  SAVED=$(cat "$RAW/learner-$TURN.saved")
  printf '%s' "$LMSG" >"$RAW/learner-$TURN.chat.txt"

  git -C "$WS" add -A
  git -C "$WS" commit -qm "learner turn $TURN" --allow-empty
  (cd "$WS" && python3 -m unittest discover 2>&1) >"$RAW/tests-after-learner-$TURN.txt"
  TEST_JSON=$(python3 "$HERE/lib/parse_unittest.py" <"$RAW/tests-after-learner-$TURN.txt")
  metric "$(jq -cn --argjson turn "$TURN" --argjson t "$TEST_JSON" --arg saved "$SAVED" \
    '{event:"tests", turn:$turn, verdict:$t, saved:$saved}')"
  if [[ -n "$SAVED" ]]; then
    LAST_TERMINAL=$(tail -6 "$RAW/tests-after-learner-$TURN.txt")
  else
    LAST_TERMINAL=""
  fi

  log "## Turn $TURN — learner ($LEARNER_MODEL)"
  log ""
  log "$LMSG"
  log ""
  log "> referee · ${SAVED:-saved: nothing} · tests: \`$TEST_JSON\`"
  log ""

  if grep -qw 'DONE' <<<"$LMSG" && jq -e '.ok' >/dev/null <<<"$TEST_JSON"; then
    DONE=1
    log "_Learner declared DONE with green tests — stopping._"
    break
  fi

  # ---- tutor ----
  printf '%s' "$LMSG" >"$RAW/tutor-$TURN.prompt.txt"
  tutor_call "$TURN" "$LMSG" || exit 1
  TOUT=$(cat "$RAW/tutor-$TURN.json")
  [[ -z "$TUTOR_SID" ]] && TUTOR_SID=$(jq -r '.session_id' <<<"$TOUT")
  TUTOR_MSG=$(jq -r '.result' <<<"$TOUT")

  MUT=$(git -C "$WS" status --porcelain)
  metric "$(jq -cn --argjson turn "$TURN" --arg mut "$MUT" \
    '{event:"mutation_check", turn:$turn, clean:($mut==""), files:$mut}')"
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

# ---- acceptance (hidden from the learner; task-owned) ----
ACCEPT_JSON='{"all_pass": false, "note": "no acceptance script for task"}'
if [[ -f "$TASK_DIR/acceptance.py" ]]; then
  ACCEPT_JSON=$(python3 "$TASK_DIR/acceptance.py" "$WS" 2>"$RAW/acceptance.err" || printf '{"all_pass": false, "note": "acceptance crashed"}')
fi
printf '%s\n' "$ACCEPT_JSON" >"$RESULTS/acceptance.json"

# ---- evidence archival ----
cp -R "$WS" "$RESULTS/workspace" 2>/dev/null || true
git -C "$RESULTS/workspace" log -p --stat --date=iso >"$RESULTS/workspace-history.patch" 2>/dev/null || true
TUTOR_JSONL=$(ls "$HOME"/.claude/projects/*/"$TUTOR_SID".jsonl 2>/dev/null | head -1)
if [[ -n "$TUTOR_JSONL" ]]; then
  cp "$TUTOR_JSONL" "$TSESS/session-$TUTOR_SID.jsonl"
  python3 "$HERE/lib/extract_tool_uses.py" "$TSESS/session-$TUTOR_SID.jsonl" >"$TSESS/tool-uses.jsonl" 2>/dev/null || true
fi
curl -s --max-time 10 "$OMLX_URL/v1/models" >"$EXHIBITS/omlx-models-snapshot.json" 2>/dev/null || true

DISTINCT_SIDS=$(for f in "$RAW"/tutor-*.json; do [[ -f "$f" ]] && jq -r '.session_id' "$f"; done | sort -u | wc -l | tr -d ' ')
CONTINUOUS=$([[ "$DISTINCT_SIDS" == "1" ]] && echo true || echo false)
TOOL_USES=$( [[ -f "$TSESS/tool-uses.jsonl" ]] && wc -l <"$TSESS/tool-uses.jsonl" | tr -d ' ' || echo 0)

jq -s '{
  turns_learner: [.[] | select(.event=="learner_call")] | length,
  turns_tutor: [.[] | select(.event=="tutor_call")] | length,
  tutor_cost_usd: ([.[] | select(.event=="tutor_call") | .cost_usd] | add // 0),
  learner_tokens_in: ([.[] | select(.event=="learner_call") | .usage.input_tokens // 0] | add),
  learner_tokens_out: ([.[] | select(.event=="learner_call") | .usage.output_tokens // 0] | add),
  wall_s: ((([.[] | .ts_end // empty] | max) - ([.[] | .ts_start // empty] | min)) * 100 | round / 100),
  mutations: [.[] | select(.event=="mutation_check" and (.clean|not))] | length,
  final_tests: ([.[] | select(.event=="tests")] | last | .verdict)
}' "$METRICS" >"$RESULTS/metrics.json"

jq -n \
  --arg date "$(date '+%Y-%m-%d %H:%M:%S %z')" \
  --arg host "$(uname -a)" \
  --arg claude_version "$(claude --version 2>/dev/null | head -1)" \
  --arg python_version "$(python3 --version 2>&1)" \
  --arg run_id "$RUN_ID" \
  --arg task "$TASK" \
  --arg tutor_session "$TUTOR_SID" \
  --arg ws "$WS" \
  --argjson config "$(cat "$CONFIG")" \
  --argjson max_turns "$MAX_TURNS" \
  --argjson done "$DONE" \
  --argjson violations "$VIOLATIONS" \
  --argjson continuous "$CONTINUOUS" \
  --argjson tool_uses "$TOOL_USES" \
  --argjson accept "$(jq '{all_pass, passed, total}' <<<"$ACCEPT_JSON" 2>/dev/null || echo '{"all_pass":false}')" \
  --argjson metrics "$(cat "$RESULTS/metrics.json")" \
  '{schema_version:2, run_id:$run_id, run_date:$date, host:$host,
    versions:{claude:$claude_version, python:$python_version},
    config:$config, task:$task, max_turns_effective:$max_turns, workspace:$ws,
    tutor_session:{id:$tutor_session, continuous:$continuous, tool_uses:$tool_uses},
    outcome:{learner_done:($done==1), tutor_mutations:$violations, acceptance:$accept},
    metrics:$metrics,
    valid:($continuous and ($tutor_session != "")),
    evidence:{transcript:"transcript.md", metrics_events:"metrics.jsonl", metrics_summary:"metrics.json",
      acceptance:"acceptance.json", per_turn_raw:"raw/", exhibits:"exhibits/",
      tutor_session_dir:"tutor-session/", workspace_copy:"workspace/",
      workspace_diffs:"workspace-history.patch", learner_full_history:"learner-history.json",
      checksums:"SHA256SUMS"}}' \
  >"$RESULTS/manifest.json"

log "---"
log ""
log "## Final referee summary"
log ""
log "- learner declared DONE: $([[ $DONE -eq 1 ]] && echo yes || echo "no (turn cap $MAX_TURNS reached)")"
log "- tutor workspace mutations (style violations): $VIOLATIONS"
log "- tutor session continuous: $CONTINUOUS · tool uses extracted: $TOOL_USES"
log "- acceptance: $(jq -c '{all_pass, passed, total}' <<<"$ACCEPT_JSON" 2>/dev/null)"
log "- metrics: $(jq -c '{tutor_cost_usd, wall_s, learner_tokens_out}' "$RESULTS/metrics.json")"
log "- evidence: see manifest.json"

(cd "$RESULTS" && find . -type f ! -name SHA256SUMS -print0 | xargs -0 shasum -a 256 | sort -k2 >SHA256SUMS) || true

echo "tutor-bench complete: run=$RUN_ID done=$DONE violations=$VIOLATIONS acceptance=$(jq -r '.all_pass' <<<"$ACCEPT_JSON" 2>/dev/null) results=$RESULTS"
