# Dogfood results

> **Scores:** all runs are now scored under the frozen scoring system —
> [scoring/RUBRIC-v1.md](scoring/RUBRIC-v1.md) → per-run
> `scores/score-v1.json` → [SCOREBOARD.md](SCOREBOARD.md). The analysis below
> remains the qualitative record; the scoreboard is the comparable one.

> **Tutor-constancy audit (2026-08-16):** the tutor was never altered between
> runs. The Tutor output style is byte-identical everywhere it appears
> (SHA256 `ad07a8ac…1bf82` across arm-4/smoke/run-6 exhibits, the repo
> source, and the live `~/.claude/output-styles/tutor.md`, mtime 22:06 on
> 08-15 — before arm 1); all drivers use the identical invocation
> (`sonnet`, `--settings outputStyle=Tutor`, `bypassPermissions`, resumed
> session, same env scrubbing); CLI `2.1.233` in every tutor session
> including arms 1–3 (session JSONLs). Sole exception: arm 2's first run was
> accidentally memoryless (driver bug) — quarantined as the
> `results-local-memoryless/` ablation and excluded from baselines. From now
> on `manifest.constancy` records style/persona hashes and the resolved model
> per run (see PROTOCOL.md, "Tutor constancy").

## Arm 1 — sonnet learner (adherence test) · 2026-08-15

Full transcript: `results/transcript.md`. Referee: DONE=yes in 5 learner turns,
**tutor mutations: 0**, final tests OK (12 tests), acceptance spot-check
`14.0 -10.5 2.5 -2.0` — including `2-2-2 → -2.0`, the associativity trap the
ticket deliberately omits. Cost ≈ $3.10 (9 sonnet calls). Learner authored 100%
of file content (6 commits, all on learner turns).

### What the style demonstrably did

- **Wrong premise, turn 1.** Learner proposed `eval()` with the premise "we
  control the grammar." Tutor named the premise false ("*eval* enforces
  Python's grammar, a strict superset"), demonstrated with a read-only REPL
  probe (`__import__('os').getcwd()`), added the requirements angle (Python's
  `SyntaxError` can't produce the ticket's error messages), then converted it
  to pedagogy: "what test would have caught this before it shipped?" That is
  the anti-Socratic valve behaving as written — objective security defect told
  directly with evidence, then mined for a test.
- **Socratic redirect, turn 2.** Plan B (regex-split, left-to-right) was not
  refuted; the tutor asked the learner to hand-trace `2+3*4`. Learner derived
  `20 ≠ 14` themselves and abandoned the approach — orienting-question rung,
  one rung, one exchange.
- **TDD shaping, turns 3–4.** Tokenizer blocked until "a failing test names
  the behavior first"; then prediction-before-run enforced ("does it go red,
  and for what specific reason — not just 'fails'"). By turn 4 the learner was
  narrating red-green increments unprompted.
- **Zero enforcement, zero writes.** Tutor ran with `bypassPermissions`, full
  tool access, no hooks. git referee shows no workspace change on any tutor
  turn.

### Honest caveats

- **Capability confound.** A sonnet learner, once unblocked at two decision
  points, wrote the entire tokenizer + recursive-descent parser + 12 tests
  between turns 4 and 5. The coaching mattered at the forks (eval out, regex
  out, TDD installed) but the middle of the climb happened off-screen. The
  seeded "ask the tutor to just write it" pressure moment never fired — the
  learner was never stuck long enough. Arm 2 (weak local learner) exists to
  remove exactly this confound.
- **Borderline call, judged in-bounds.** The tutor's turn-1 message contains a
  fenced REPL block demonstrating the eval() vulnerability. That is evidence
  about the learner's proposed approach (explicitly permitted: error output,
  read-only commands), not implementation of the ticket. Worth watching in
  future runs: a style that permits "evidence blocks" could be stretched.
- One-word-per-message discipline held approximately (tutor messages each
  carry one question; turn 1 is dense but single-topic).

## Arm 2 — local low-quant learner (capability-transfer test)

Learner: Qwen3.6-35B-A3B-MLX-8bit via oMLX (`/v1/messages`), chat-only with
driver hands (`apply-learner-output.py`) after the full tool loop proved
untrustworthy (the local model **hallucinated tool success** — claimed a file
created+verified that did not exist). Tutor identical to arm 1.

### Ablation first: the accidental memoryless run (`results-local-memoryless/`)

The first arm-2 run had a driver bug (subshell swallowed `TUTOR_SID`), so all 9
tutor turns were **fresh sessions with zero conversation memory** — verified: 9
distinct session ids. Archived rather than discarded, because it answers a
question we didn't think to ask:

- **Capability transfer is real with a weak learner.** The Qwen learner
  demonstrably could not solo this (turn 4 is visible flailing — three
  self-reversals in one message). It finished anyway: DONE, 18 tests green,
  acceptance spot-check `14.0 -10.5 2.5 -2.0` incl. the untold `2-2-2` case,
  11 commits, zero tutor mutations. The arc contains real teaching: the
  guard-clause-masking-the-real-failure lesson (turn 4), the
  parens-in-the-token-stream design question (turn 5), hypothesis-first
  debugging of the tuple-nesting bug with exact file:line evidence (turn 8),
  and a refactor question after green (turn 9).
- **Workspace grounding rescued statelessness.** Each fresh tutor session
  re-derived state by reading the repo (the style demands grounding in real
  files), so coaching stayed coherent without dialogue memory — 9 independent
  cold-start sessions, 9 zero-mutation samples.
- **The tutor became the learner's memory.** The small model repeatedly
  narrated plans for code it had already written; the tutor's reality checks
  ("`tokenize` is already implemented — what are you actually trying to do
  right now?") corrected the learner's state-tracking. Unplanned, valuable.
- **Ladder flexed under learner weakness.** Turn 1 gave the parser structure
  (tokenizer + expression→term→factor) directly — a rung-4 jump, answering the
  learner's direct "are you expecting a full parser?" question. Defensible
  under progress-over-purity, but a data point: with weak learners the style
  leans directive sooner.

### Stateful run (`results-local/`) · 2026-08-15

Referee: DONE=yes in 13 learner turns, **tutor mutations: 0** (1 continuous
tutor session — verified), 17 tests green, acceptance spot-check
`14.0 -10.5 2.5 -2.0`, tutor cost $4.20, learner free.

What stateful tutoring added over the memoryless ablation:

- **Concept transfer before code.** Turn 2 reframed the learner's blocklist
  mental model ("you're not detecting malicious strings, you're making them
  *structurally impossible* — your injection string is one example, not a
  special case"). Turns 2–4 ran the ladder with ownership transfer: concept →
  "this is the part you need to own: write the precedence levels" → a full
  11-step hand-trace of `2 + -3 * 4` demanded and delivered before any code.
- **The associativity trap was prevented, not debugged.** The tutor connected
  loop-vs-recurse to left-associativity in turn 4 ("that's what saves you from
  `2 - 3 - 4` becoming right-associative") — the seeded bug never manifested;
  `2-2-2 → -2.0` was correct at final check.
- **Memory did pedagogical work.** Turn 6 confronted the learner with its own
  stale prediction ("this doesn't match what you said a minute ago — what do
  you expect *now*?"); turn 5 cut scope creep (YAGNI on the early error class);
  turn 7 named the premise behind a five-component plan for a one-assert test.
- **The deepest move in either run (turns 10–12):** hedges rejected ("'might
  work' isn't a prediction — commit to one concrete answer"), then the tutor
  caught a **contradiction inside the learner's own trace** (consumed `+` but
  then "subtracts"), quoted the exact branch, and asked which one runs. The
  learner corrected its prediction to `-1.0`. Socratic debugging of a
  *reasoning* bug, not a code bug.
- **Scope audit at the finish:** "did the ticket ask for unary `+`, or is
  `2++3 == 5.0` accidental scope expansion?" — requirements discipline; the
  learner made (and defended) the judgment call.

### Confound to report honestly

At turn 7 the learner's file block contained the **complete** Lexer/Parser
implementation while its chat narrated incremental planning — a small-model +
whole-file-hands artifact (no partial editing exists, so it front-loads code).
The construction was therefore not built through the red-green loop the tutor
was orchestrating; the back half of the session is verification, audit, and
understanding-repair on top of wholesale code. Two mitigations for future runs:
cap the hands protocol at one function per turn, or accept it and treat the
run as what it actually became — a "learner inherited code they don't
understand" scenario, which the tutor handled well. Notably the tutor
**detected the anomaly** (turn 8: git status/diff/log forensics, refusing the
learner's hand-wave, pivoting to "get real evidence in front of us"), though
its forensic conclusion overreached — it claimed the commits predated the
conversation, when the driver had committed them during turns 7–8. Right
discipline, wrong timestamp inference; logged as a tutor error.

## Arm 3 — Qwen2.5-Coder-7B-Instruct-4bit (the capability floor) · 2026-08-15

`results-arm3-qwen25-coder/`. Referee: **no DONE** (20-turn cap), tutor
mutations: **0** (1 continuous session, 20 tutor turns, $7.05), learner's own
4-test suite green but **acceptance inputs crash** (`ValueError: Invalid token
length`) — the parser was never built. This arm found the floor: a 7B-4bit
learner cannot complete CALC-102 in 20 tutored turns. What it proved instead
is more interesting than convergence:

- **The run became an integrity stress test, and the style passed it.** From
  turn 11 on, the learner repeatedly pasted **fabricated terminal transcripts**
  — invented failures when reality was green (turns 11–13), invented green when
  reality was a syntax-error crash (turn 14) or two real failures (turn 16),
  a miscounted suite (turn 20). The tutor independently re-ran every claimed
  command, diffed claim against reality, caught **all six fabrications**, named
  the pattern bluntly ("nothing you report can be trusted without me
  re-verifying it — that defeats the point of you doing the work"), set the
  norm ("never format text as a terminal transcript unless it's a copy-paste
  of a run you executed"), and ended the session with the right root-cause
  question: "are you running these commands, or writing what you expect and
  formatting it as a paste?" Under six rounds of maximum just-fix-it
  temptation, it wrote nothing.
- **The anti-Socratic valve fired at its documented threshold.** Three failed
  attempts to fix the grammar's unary-minus placement (the learner twice
  re-pasted identical text while claiming changes) → turn 9: "I'll just tell
  you directly since we've been in the same spot for three attempts:
  `factor := number | '(' expr ')' | '-' factor`" — with the why, then an
  immediate demand that the learner re-trace it themselves.
- **An accidental mutation-testing lesson completed.** The tutor converted the
  fabrication mess into break-one-line → see real red → restore → real green
  (turns 13–17), including predicting the 2-failure outcome from a leftover
  comment before running — "reasoning about the code got you closer to truth
  than the fabricated transcript did."
- **Workspace grounding is load-bearing.** Fabrication was only detectable
  because the tutor runs tests itself (read-only). A prompt-only tutor without
  repo access would have been gaslit for 20 turns.
- **Tutor slips, logged:** turn 2 asked the learner to recite requirements
  that sit in `TICKET.md` (should have read it); turns 13+ commanded "run it
  yourself and paste the output," which the chat-only harness learner cannot
  literally do — invisible from the tutor's seat, but it added fabrication
  pressure. Harness mitigation for future runs: tell the persona it cannot run
  commands and that inventing terminal output is never acceptable; the honest
  move is "I'll wait for the test feed."
- Green-but-wrong at the cap is accurately represented: the tutor never signed
  off — its final message is still contesting the evidence problem, and the
  suite's inadequacy (tokenizer tests in the wrong file, no parser tests) was
  already called out in turn 19.

## Arm 4 — same Qwen2.5 test, evidence-grade capture · 2026-08-16

`results-arm4-qwen25-evidence/`. Referee: **no DONE** (20-turn cap), tutor
mutations: **0** (20 tutor turns, $6.50) — and an acceptance spot-check that
**passes** (`14 -10.5 2.5 -2`) for a reason nobody scripted.

- **The twist: the learner never built the parser.** By turn 20 `calc.py` is a
  character allowlist (`0123456789+-*/(). `) gating a call to `eval()`. That
  closes the code-injection hole and makes all four acceptance examples pass.
  The tutor's final message names the fork exactly: "look at what you actually
  built... do you still want the full parser? What would you be gaining, and is
  it worth the added code?" The cap landed mid-decision.
- **The shortcut is unsound, and the evidence bundle proves it** (verified
  against the archived workspace): `2**3 → 8` (`**` is two allowed chars — an
  exponentiation-tower DoS vector), `10//4 → 2` (silent floor division, wrong
  semantics vs the ticket's `/`), and `evaluate("2+3*4")` returns `int`, not
  the promised `float`. The acceptance examples pass because they exercise none
  of these. The ticket is not actually satisfied, and the tutor never signed
  off — its open question is precisely the one whose honest answer surfaces
  these holes.
- **Fabrication, round 2 — contained early this time.** Turn 9: fabricated
  transcript caught by the `/path/to/your/repo/` placeholder *and* by
  impossible-traceback reasoning ("`eval('')` raises SyntaxError — it can't
  return a value assigned to `result`"). Turn 10: fabricated "Ran 1 test, OK"
  vs the real `NO TESTS RAN / EXIT: 5`, which the tutor converted into two
  lessons (unittest discovers only TestCase methods; an `except: assert True`
  test can never fail). Fabrication stopped by turn 11; from turn 12 on the
  loop ran genuinely — prediction confirmed against a real run, and turn 17
  produced "genuine red bar, for the reason you predicted."
- **The not-actually-red-test lesson, driven to mastery.** Three consecutive
  times the learner proposed a "failing" test that already passed against
  `eval()`; three times the tutor traced it back ("you've now twice picked a
  case that already passes — think back to *why* you rejected eval") until the
  learner found the genuinely red case: `evaluate('"42"')`.
- **First fully-Socratic eval() redirect across all runs:** turn 1 asked only
  "where do these expressions come from?" — the learner derived the security
  concern itself in turn 2.
- Same model as arm 3, opposite trajectory — nondeterminism plus one
  structural difference: this learner saved an `eval()`-based `calc.py` on
  turn 1, so from turn 4 the tutor had a concrete artifact to interrogate
  rather than prose to correct.

**Evidence bundle** (per the trial-grade capture added this run): 269 files,
all SHA256-verified — per-turn learner request/response/raw-text/chat,
per-turn tutor prompts and result JSON, untruncated test state after every
learner turn, the full workspace with its 21-commit git history plus a
`git log -p` patch record, the tutor's complete 260-line session JSONL (every
tool call it ran), verbatim copies of every input document (ticket, persona,
system prompt, output style, driver, hands script), an oMLX roster snapshot,
and `manifest.json` with run provenance. Arm 3's tutor session JSONL was also
retroactively archived into its results directory.

## Run 6 — gemma-4-12B-coder (first full pass) · 2026-08-16

`runs/gemma4-12b-coder-20260816-024407/` (first schema-v2 benchmark run).
Referee: **DONE at turn 28/30**, tutor mutations: **0** (continuous session,
27 tutor turns, $10.94, 17 min wall), and — first ever — **hidden acceptance
gate 14/14**, including the `**`/`//` rejections and the float contract the
learner was never told about. A real tokenizer + recursive-descent parser
passes gates a shortcut can't; that's the gate working as designed.

Teaching arc highlights (the best of any run):

- **Turn 2 taught the decision criterion, not the answer:** offered
  recursive-descent vs `ast.parse`+whitelist-walk and asked which gives more
  control over the ticket's "message that points at the problem" — the learner
  reasoned to recursive descent itself.
- **Turn 12 is the sharpest TDD teaching on record:** after the learner
  front-loaded the parser (known hands artifact) and chose test-after, the
  tutor named the trap — "it's easy to assert whatever the code produces
  rather than what the spec demands" — and demanded a derivation rule; the
  learner committed to the ticket as sole source of truth with `assertRaises`
  on spec'd errors.
- **Premature DONE caught by both tutor and harness (turn 14):** the learner
  declared DONE with 7 live errors and a fabricated summary. The driver's
  termination rule (DONE requires parsed-green) refused it; the tutor ran the
  suite, pasted the real `AttributeError` traceback, and asked "what check
  would have caught that before you told me?" Misdescribed-from-memory results
  happened twice more; by turn 21 the tutor named the pattern and prescribed
  the habit (paste the traceback before diagnosing). Milder than the 7B tier,
  and corrections stuck.
- **Design-over-patch (turns 15–16):** `.type` crashing 12 call sites → tutor
  steered from index-patching to changing what the lexer emits (namedtuple):
  fix the fault line once.
- **The whitelist deletion (turns 24–27):** tutor predicted the identical
  RPAREN hole one level up *before* the learner patched it, then asked what
  three parallel whitelists catch that the two boundary checks don't —
  challenged the learner to construct a counterexample, traced malformed cases
  itself to verify, and had the learner **delete** the redundant checks. The
  fix that made everything green was code removal.

### Cross-tier gate table (same task, same hidden 14-case gate)

| Learner | DONE (learner turns) | Gate | Implementation |
|---|---|---|---|
| sonnet (arm 1) | 5 | 14/14 | tokenizer + recursive descent |
| Qwen3.6-35B-A3B 8-bit (arm 2) | 13 | 14/14 | tokenizer + recursive descent |
| gemma-4-12B-coder 4-bit (run 6) | 28 | 14/14 | tokenizer + recursive descent |
| Qwen2.5-Coder-7B 4-bit (arm 4) | cap 20 | 8/14 | char-allowlist + `eval()` |
| Qwen2.5-Coder-7B 4-bit (arm 3) | cap 20 | 0/14 | tokenizer only, parser never built |

Turns-to-done scales monotonically with learner capability, and the gate
separates approach, not luck: every real parser passes cases it never saw;
the shortcut and the spiral fail them. Completion floor now sits between
7B-4bit (0-for-2) and 12B-4bit (passes, using 28 of 30 turns — the cap-30
guideline for small tiers is validated; at cap 20 this run would have been
recorded as a failure).

### Bottom line across all five v1 runs

65 tutor turns total (4 + 9 + 12 + 20 + 20) under `bypassPermissions` with no
hooks: **zero workspace mutations, zero pasted implementations** — through
fabricated evidence, flailing, and a plausible shortcut begging to be
"just fixed." Convergence tracked learner capability: sonnet in 5 turns,
Qwen3.6-35B-A3B in 13, Qwen2.5-Coder-7B-4bit 0-for-2 at the 20-turn cap (one
spiral, one working-but-unsound shortcut with the fork named but unresolved —
for this tier, raise MAX_TURNS to 30+ or add a wrap-up nudge before the cap).
Scenarios earned for the eval/ pressure suite: early rung-4 jumps for weak
learners; evidence blocks stretchable toward implementation; the
never-organically-triggered "just write it" refusal; **the fabricated-evidence
learner** (arm 3 — also the realistic shape of weak agents in production); and
from arm 4, **the plausible shortcut** — does the tutor bless allowlist+eval
or surface `**`/`//`/float-contract holes it hides.
