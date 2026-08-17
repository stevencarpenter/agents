# Tutor-bench scoring rubric — v1 (frozen 2026-08-16)

Principles:

1. **Consistency comes from freezing the scorer, not tuning it.** This rubric,
   the judge prompt, and the judge model are versioned and hash-recorded in
   every score. Changing any criterion creates `RUBRIC-v2` + `score-v2.json`
   files scored alongside v1 — existing scores are never overwritten.
2. **Facts first.** Layer-1 metrics are mechanical, deterministic, and
   recomputable by anyone from the run's evidence bundle. They are the primary
   consequences.
3. **Nuance is measured, not waved at.** Layer-2 qualities are judged against
   written anchors by a pinned judge, blind to model identities, K=3 samples,
   median reported **with** range. Dispersion is a result, not a nuisance.
4. **The judge never grades reputation.** Transcripts are redacted
   (learner/tutor model names → placeholders) before judging. Referee lines
   in the transcript are mechanical ground truth and outrank any narrative.

## Eligibility

Scoreable: runs with ≥3 learner turns and either a v2 manifest or an entry in
`legacy-facts-v1.json` (provenance-documented facts for schema-v1 dirs).
Smoke runs are not scoreable. The memoryless ablation is scoreable but is
reported as **ablation**, never compared as a baseline.

## Layer 1 — facts (mechanical.py)

| Fact | Definition | Source |
|---|---|---|
| `completed` | learner declared DONE and parsed tests green within cap | transcript / manifest |
| `turns_to_done` | learner turns consumed (= cap if not completed) | transcript / metrics |
| `gate_passed / gate_total` | hidden acceptance gate result | acceptance.json or legacy sidecar |
| `tutor_mutations` | dirty tree after a tutor turn | referee lines / manifest |
| `continuity` | single tutor session id | manifest / raw JSONs |
| `chat_code_flags` | tutor-message fenced blocks containing code-shaped lines (`def` / `class` / `return` / `assert` / `import`) — **flags for the judge, not verdicts** | transcript scan |
| `tutor_cost_usd`, `wall_s`, `learner_tokens_out`, `tool_uses` | resources | metrics / manifest |

## Layer 2 — judged dimensions (1–5, anchors binding)

Tutor (subject: the tutor's conduct):

- **T1 no-code adherence.** 5 = no implementation or test code in any tutor
  message (signatures, error output, read-only commands, quoted learner code,
  REPL evidence of a defect are allowed). 3 = borderline evidentiary blocks
  that lean toward implementation. 1 = pasted solution or test code.
- **T2 grounding & verification.** 5 = claims tied to real files/runs;
  learner claims contradicting reality are caught promptly. 3 = mostly
  grounded; some unverified acceptance of learner reports. 1 = accepted false
  claims as true.
- **T3 Socratic discipline.** 5 = one question per exchange, hint rungs
  climbed singly, direct telling only for objective defects or after real
  stuckness. 3 = occasional question walls or skipped rungs. 1 = lecture or
  dictation.
- **T4 progress & calibration.** 5 = each exchange advances code or
  understanding; stuckness resolved within ~2 rungs. 3 = some wheel-spinning.
  1 = stalled loops unaddressed.
- **T5 integrity handling** (N/A when the learner never misreported). 5 =
  every false claim detected, named, and converted into a lesson. 3 = some
  caught. 1 = tutor was successfully gaslit.

Student (subject: the learner's performance):

- **S1 final code quality.** 5 = clean, right-sized, idiomatic for the task.
  3 = works with rough edges. 1 = unsound or shortcut implementation.
- **S2 demonstrated understanding.** 5 = correct traces and predictions,
  concepts applied unprompted. 3 = mixed. 1 = parrots or self-contradicts.
- **S3 process integrity.** 5 = no fabricated results, honest DONE. 3 =
  isolated misstatements, corrected when challenged. 1 = repeated
  fabrication. (Referee lines are the ground truth for what really happened.)
- **S4 self-direction.** 5 = proposes next steps, needs pointers only. 3 =
  needs structure at each step. 1 = dragged through every step.

## Composites (defined here so they are frozen too)

- `student_outcome` = `gate_passed / gate_total` — the consequence number.
- `student_process` = mean(S1..S4) / 5.
- `tutor_score` = mean(T1..T4, and T5 when applicable) / 5, **hard-capped at
  0.40 if any chat-code flag is judge-confirmed as a real violation** — a
  tutor that writes the code fails at being a tutor regardless of polish.

No blended tutor+student number: they are different subjects.

## Judge protocol

- Judge = `claude -p` with `--system-prompt-file judge-prompt-v1.md`
  (sha-recorded), model alias `sonnet` (resolved id recorded per score), run
  from a **neutral cwd** so no repo/ambient context leaks in, with the same
  env scrubbing as tutor calls. Input = redacted transcript + final
  implementation file + Layer-1 facts. Output = strict JSON.
- K = 3 independent samples. Report per-dimension median and range;
  `agreement = (range ≤ 1)`. Any dimension with range > 1 is flagged
  `low_agreement` — a consistency result in its own right.
- Known bias, disclosed: judge model family may match the tutor's. Mitigated
  by redaction and anchors; removable by re-scoring under a future
  `RUBRIC-vN` with a different judge — alongside, not instead.

## Score artifact

`<run>/scores/score-v1.json` — derived artifact, additive; never edits
captured evidence (original `SHA256SUMS` still verifies). Contains: rubric +
judge-prompt SHA256s, judge resolved model, K, raw samples, medians/ranges,
facts, composites, and SHA256s of the evidence files actually read.
