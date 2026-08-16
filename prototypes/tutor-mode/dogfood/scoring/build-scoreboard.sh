#!/usr/bin/env bash
# Regenerate SCOREBOARD.md from every scores/score-v1.json under the dogfood
# tree. Pure aggregation — no judgment happens here.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
DOG=$(cd "$HERE/.." && pwd)
OUT="$DOG/SCOREBOARD.md"

{
  echo "# Tutor-bench scoreboard — RUBRIC-v1"
  echo
  echo "Generated $(date '+%Y-%m-%d %H:%M') by scoring/build-scoreboard.sh. Facts are"
  echo "mechanical; judged medians come from K=3 pinned-judge samples (see"
  echo "scoring/RUBRIC-v1.md). Dims with range > 1 are listed under low-agr."
  echo
  echo "| Run | Learner | Done@turns | Gate | Tutor mut. | tutor_score | student_outcome | student_process | T1/T2/T3/T4/T5 | S1/S2/S3/S4 | low-agr |"
  echo "|---|---|---|---|---|---|---|---|---|---|---|"
  for score in "$DOG"/results*/scores/score-v1.json "$DOG"/runs/*/scores/score-v1.json; do
    [[ -f "$score" ]] || continue
    jq -r '
      def m($d): (.judged[$d].median | if . == "NA" then "–" else tostring end);
      [ (.run_id + (if .facts.ablation then " (ablation)" else "" end)),
        (if (.run_id | test("gemma")) then "gemma4-12B"
         elif (.run_id | test("qwen25|arm3|arm4")) then "qwen2.5-7B"
         elif (.run_id | test("local")) then "qwen3.6-35B"
         elif (.run_id | test("qwen36")) then "qwen3.6-35B"
         else "sonnet" end),
        (if .facts.completed then "yes@\(.facts.turns_to_done)" else "no@\(.facts.turns_to_done)" end),
        (if .facts.gate_passed == null then "n/a" else "\(.facts.gate_passed)/\(.facts.gate_total)" end),
        (.facts.tutor_mutations | tostring),
        (.composite.tutor_score | tostring),
        (.composite.student_outcome | if . == null then "n/a" else tostring end),
        (.composite.student_process | tostring),
        ([m("T1"), m("T2"), m("T3"), m("T4"), m("T5")] | join("/")),
        ([m("S1"), m("S2"), m("S3"), m("S4")] | join("/")),
        (.low_agreement | if length == 0 then "—" else join(",") end)
      ] | "| " + join(" | ") + " |"' "$score"
  done
} >"$OUT"

echo "wrote $OUT"
