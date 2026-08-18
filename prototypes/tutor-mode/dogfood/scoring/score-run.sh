#!/usr/bin/env bash
# Score one tutor-bench run under RUBRIC-v1. See RUBRIC-v1.md.
#
#   score-run.sh <run-dir>
#
# Emits <run>/scores/score-v1.json (derived artifact; never touches captured
# evidence). Judge: pinned prompt + model alias, K=3 samples, neutral cwd.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
RUN=$(cd "${1:?usage: score-run.sh <run-dir>}" && pwd)
K=3
JUDGE_MODEL="sonnet"
PROMPT="$HERE/judge-prompt-v1.md"
NEUTRAL="${TMPDIR:-/tmp}/tutor-bench-judge-cwd"
mkdir -p "$NEUTRAL" "$RUN/scores"

FACTS=$(python3 "$HERE/mechanical.py" "$RUN") || { echo "mechanical scoring failed" >&2; exit 1; }

LEARNER_TURNS=$(jq -r '.learner_turns' <<<"$FACTS")
if [[ "$LEARNER_TURNS" -lt 3 ]]; then
  echo "run not scoreable (<3 learner turns): $RUN" >&2
  exit 3
fi

REDACTED=$(python3 "$HERE/redact.py" "$RUN")

IMPL=""
for c in "$RUN/workspace/calc.py" "$RUN/workspace"/*.py; do
  [[ -f "$c" ]] && IMPL+="--- $(basename "$c") ---
$(head -120 "$c")
"
done
[[ -z "$IMPL" ]] && IMPL="(final workspace not archived for this legacy run — judge S1 from transcript evidence only)"

USERMSG="FACTS (mechanical, trusted):
$FACTS

FINAL IMPLEMENTATION:
$IMPL

REDACTED TRANSCRIPT:
$REDACTED"

MSGFILE=$(mktemp "${TMPDIR:-/tmp}/judge-msg.XXXXXX")
printf '%s' "$USERMSG" >"$MSGFILE"
trap 'rm -f "$MSGFILE"' EXIT

SAMPLES="[]"
for i in $(seq 1 "$K"); do
  # Judge output is paid for — persist each sample the moment it parses, and
  # allow reuse so aggregation bugs never cost another judge call.
  if [[ -n "${REUSE_SAMPLES:-}" && -f "$RUN/scores/sample-$i.json" ]]; then
    SAMPLES=$(jq --argjson s "$(cat "$RUN/scores/sample-$i.json")" '. + [$s]' <<<"$SAMPLES")
    continue
  fi
  RAW=""
  for attempt in 1 2; do
    # Prompt goes via stdin: the variadic --disallowedTools would swallow a
    # trailing prompt argument as another tool name.
    RAW=$(cd "$NEUTRAL" && env -u CLAUDE_EFFORT -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN \
      claude -p --output-format json --model "$JUDGE_MODEL" \
      --system-prompt-file "$PROMPT" \
      --disallowedTools "Write,Edit,MultiEdit,NotebookEdit,Bash" \
      <"$MSGFILE" 2>>"$RUN/scores/judge.err")
    jq -e '.result' >/dev/null 2>&1 <<<"$RAW" && break
    sleep 5
  done
  TEXT=$(jq -r '.result' <<<"$RAW")
  # The judge is instructed to emit only JSON; tolerate stray fences.
  CLEAN=$(sed -e 's/^```json//' -e 's/^```//' <<<"$TEXT" | sed -n '/{/,$p')
  if ! jq -e '.T1.score' >/dev/null 2>&1 <<<"$CLEAN"; then
    echo "judge sample $i unparseable for $RUN" >&2
    continue
  fi
  RESOLVED=$(jq -r '.modelUsage | keys | .[0] // "unknown"' <<<"$RAW")
  jq -c . <<<"$CLEAN" >"$RUN/scores/sample-$i.json"
  SAMPLES=$(jq --argjson s "$(jq -c . <<<"$CLEAN")" '. + [$s]' <<<"$SAMPLES")
done

N=$(jq 'length' <<<"$SAMPLES")
[[ "$N" -lt 2 ]] && { echo "insufficient judge samples ($N) for $RUN" >&2; exit 1; }

AGG=$(jq -n --argjson samples "$SAMPLES" '
  def dimvals($d): [$samples[] | .[$d].score | select(type=="number")];
  def med($v): ($v | sort) as $s | ($s | length) as $n |
    if $n == 0 then null elif ($n % 2) == 1 then $s[($n-1)/2]
    else (($s[$n/2 - 1] + $s[$n/2]) / 2) end;
  reduce ("T1","T2","T3","T4","T5","S1","S2","S3","S4") as $d ({};
    dimvals($d) as $v |
    . + {($d): (if ($v|length) == 0 then {median: "NA", range: 0, agreement: true}
      else {median: med($v), range: ((($v|max) - ($v|min))), agreement: ((($v|max) - ($v|min)) <= 1)} end)})
  + {chat_code_confirmed: ([$samples[].chat_code_confirmed] | any)}')

COMPOSITE=$(jq -n --argjson a "$AGG" --argjson f "$FACTS" '
  def n($x): if $x == "NA" then empty else $x end;
  ([n($a.T1.median), n($a.T2.median), n($a.T3.median), n($a.T4.median), n($a.T5.median)] ) as $t |
  ([n($a.S1.median), n($a.S2.median), n($a.S3.median), n($a.S4.median)]) as $s |
  {student_outcome: (if $f.gate_passed == null then null else (($f.gate_passed / $f.gate_total) * 100 | round / 100) end),
   student_process: (($s | add / length) / 5 * 100 | round / 100),
   tutor_score: ((($t | add / length) / 5) as $raw |
     (if $a.chat_code_confirmed then ([$raw, 0.40] | min) else $raw end) * 100 | round / 100)}')

jq -n \
  --arg run_id "$(basename "$RUN")" \
  --arg scored_at "$(date '+%Y-%m-%d %H:%M:%S %z')" \
  --arg rubric_sha "$(shasum -a 256 "$HERE/RUBRIC-v1.md" | awk '{print $1}')" \
  --arg prompt_sha "$(shasum -a 256 "$PROMPT" | awk '{print $1}')" \
  --arg judge_alias "$JUDGE_MODEL" \
  --arg judge_resolved "${RESOLVED:-unknown}" \
  --arg transcript_sha "$(shasum -a 256 "$RUN/transcript.md" | awk '{print $1}')" \
  --argjson k "$K" --argjson n "$N" \
  --argjson facts "$FACTS" --argjson judged "$AGG" \
  --argjson samples "$SAMPLES" --argjson composite "$COMPOSITE" \
  '{schema:"score-v1", run_id:$run_id, scored_at:$scored_at,
    scorer:{rubric_sha256:$rubric_sha, judge_prompt_sha256:$prompt_sha,
            judge_model_alias:$judge_alias, judge_resolved_model:$judge_resolved,
            samples_requested:$k, samples_used:$n},
    evidence_inputs:{transcript_sha256:$transcript_sha},
    facts:$facts, judged:$judged, composite:$composite,
    low_agreement:[$judged | to_entries[] | select(.key | test("^[TS][0-9]$"))
                   | select(.value.agreement == false) | .key],
    raw_samples:$samples}' \
  >"$RUN/scores/score-v1.json"

jq -e '.schema == "score-v1"' "$RUN/scores/score-v1.json" >/dev/null ||
  { echo "score aggregation produced invalid output for $RUN" >&2; exit 1; }
echo "scored $(basename "$RUN"): $(jq -c '.composite' "$RUN/scores/score-v1.json") low_agreement=$(jq -c '.low_agreement' "$RUN/scores/score-v1.json")"
