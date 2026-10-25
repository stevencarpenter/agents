---
name: blind-review
description: "Experimental paired code review with comments and docstrings removed from one pass. Use when the user asks for a blind review, a mechanical changed-lines-only review, a comment-versus-code check, or a paired review experiment."
---

# Blind Review (PoC)

**Status: proof of concept.** This skill tests whether comments and docstrings
bias LLM reviewers. The paired output and JSONL log compare reviews with and
without that context. State in the report that findings are experimental.

## Modes

- **Primary** (default): run both passes, present the merged report.
- **Sidecar** (when the user asks to collect paired data alongside another
  review): run both passes read-only, log the pair record,
  and give only a one-line summary: do not editorialize on the primary
  task's review.

Flag: **`--mechanical`** (also "mechanical", "maximally blind"). Applies to
either mode and changes only the blind arm. Each reviewer receives the changed
code lines of one file and nothing else: no unchanged lines, no comments,
docstrings, TODOs, or docs, no whitespace-only edits, no file path, no tools,
and no harness customizations. Use it to review the change in the most
mechanical sense. Steps 2 and 3 have a mechanical variant; the other steps
are unchanged.

## Workflow

### 1. Determine the target

Default: the working diff against `HEAD` (in jj-colocated repos `git diff`
still reads fine: this flow never mutates the repo). The user may name a
base ref, branch, or PR instead; resolve PRs to a local ref first.

### 2. Strip

```bash
<this-skill-dir>/scripts/strip_context.py diff \
  --repo <repo> --base <ref> --out <scratchpad>/blind-review-<short-id>
```

The out dir MUST be outside the reviewed repo, such as in the session scratchpad.
Strip output inside the worktree shows up as untracked files in
the context pass, revealing the experiment and contaminating the control
arm. This writes `base/`, `head/`, `stripped.diff`, and `manifest.json`
into the out dir. Line and column numbers are preserved (comments become spaces,
docstrings become `""`), so stripped findings cite real source locations.
Check `manifest.json`: files marked `copied-verbatim` were NOT stripped
(unknown language or parse error): tell the blind reviewer to skip them
and disclose the gap in the report.

**Mechanical strip** (with `--mechanical`, instead of the command above):

```bash
<this-skill-dir>/scripts/strip_context.py mechanical \
  --repo <repo> --base <ref> --out <scratchpad>/blind-review-<short-id>
```

This writes `units/fNN.<ext>.diff` (one per file: `-N|line` and `+N|line`
rows with original line numbers) and `manifest.json` (the label-to-path map).
It writes no `base/` or `head/` tree. Files the stripper cannot clean are
omitted, not copied verbatim; report every `omitted` manifest entry as
unreviewed. A file whose only edits are comments or spacing becomes
`no-code-change` and gets no unit.

### 3. Run both passes in parallel: one message, two agents

**Blind pass**: spawn the `blind-reviewer` agent (fall back to a
general-purpose read-only agent carrying the same brief if unregistered).
Start a fresh agent without inherited conversation or repository instructions.
Give it ONLY the out dir: review `head/` with `stripped.diff` as the
change under review. Never mention the original repo path, repo name, or
branch: the isolation is the experiment. It cannot be hard-sandboxed, so
the prompt must not leak paths it could follow back.

**Mechanical blind pass** (with `--mechanical`): spawn `blind-reviewer`
with ONLY this brief: "Mechanical mode. Run
`<this-skill-dir>/scripts/mechanical_review.py --out <out-dir> --model <m>
--effort <e>` and merge `<out-dir>/results/*.json`." The agent reviews
nothing itself. The script gives each unit to a separate headless
`claude -p` process (no tools, `--safe-mode`, no settings, MCP servers, or
skills, a fixed system prompt, one fixed empty working directory) and records
the exact payload in `payloads/` so the isolation can be audited. Map the
returned `fNN` labels back to paths with `manifest.json` yourself; never give
the manifest to the agent. After a Claude Code upgrade, run
`<this-skill-dir>/scripts/audit_request.py --out <out-dir>`: it captures the
full request the CLI sends (no model call), fails on any repo-name leak, and
lists every field that differs between two identical runs.

**Context pass**: use the superpowers
requesting-code-review flow or /code-review conventions, or a
language-appropriate reviewer agent on the real repo with full context.
Do not tell the context reviewer about the blind pass, and confirm its
prompt and environment carry zero trace of the experiment (no strip
output, no scratch paths, no experiment vocabulary). Give BOTH arms the
identical review-priority checklist: if only the blind arm gets a
structured checklist, any blind-arm lift may just be "checklist beats
freeform review", not de-biasing.

Keep both passes on the same model and effort: mismatched arms confound the
comparison. Verify candidate findings against the original source before reporting them.

### 4. Merge into four buckets

- **[both]**: found by both passes; still requires source verification.
- **[blind-only]**: found only by the blind pass. Verify whether the difference
  comes from misleading comments or a false positive in step 5.
- **[context-only]**: findings that required docs/comments/repo context.
- **[divergence]**: produced by step 5.

Match findings across passes by file:line proximity and described failure
mode, not exact wording.

### 5. Divergence pass

For each [blind-only] finding and each finding the blind pass tagged
`assumption:`, read the ORIGINAL file at those lines and compare the
comments/docstrings against the blind description of what the code does.
A comment that contradicts executable behavior is a **[divergence]** finding.
Examples include "validated above" with no validation or "cannot overflow"
with an unchecked add. A single pair does not establish why one reviewer missed it.

### 6. Log the pair record (both modes, including sidecar)

```bash
<this-skill-dir>/scripts/log_pair.py <record.json>
```

Record shape (append-only JSONL at `~/.local/share/blind-review/pairs.jsonl`):

```json
{
  "run_id": "<id>", "repetition_index": 0,
  "repo": "<name>", "base": "<ref>", "target": "<diff|files>",
  "blind_mode": "<stripped|mechanical>",
  "diff_hash": "<sha256 of the reviewed diff>",
  "strip_manifest_ref": "<path: exclude copied-verbatim files from analysis>",
  "models": {"blind": "...", "context": "..."},
  "cost": {"blind_tokens": 0, "context_tokens": 0},
  "traps": [{"id": "...", "file_line": "...", "category": "...",
             "description": "...", "proof": "<executable check ref>"}],
  "blind_findings": [{"file_line": "...", "claim": "...",
                      "matched_trap_id": null, "verdict": "hit|partial|miss"}],
  "context_findings": [...],
  "buckets": {"both": 0, "blind_only": 0, "context_only": 0, "divergence": 0},
  "grader_blinded": true,
  "notes": "<anything anomalous>"
}
```

`traps[]` + per-finding `matched_trap_id`/`verdict` are what make the log
analyzable (detection rates, paired 2×2) instead of descriptive: omit
them only for non-synthetic runs with no ground truth. When grading
against ground truth, blind the grader: normalize findings (strip
provenance tags like `assumption:`, arm-specific formatting tells),
shuffle across arms, grade against the trap key, and only then rejoin the
arm mapping. An unblinded grader credits the arm it expects to win.

### 6b. Track the mechanical reviewer (with `--mechanical`)

Two records, for two questions:

- **Score (benchmark):** does the reviewer find planted defects without
  false alarms, and how stable is it across reps? After any change to the
  brief, schema, stripper, model, or effort, run
  `<this-skill-dir>/bench/bench.py run --record` and commit the new line in
  `bench/results.jsonl`. `bench.py summary` prints the history.
- **Effectiveness (real use):** did findings on real changes help ship
  better code? Run `<this-skill-dir>/scripts/review_log.py log --out
  <out-dir>` after each real run. When the user fixes or dismisses a
  finding, record it with `review_log.py mark <id>
  accepted|false-positive|not-useful|duplicate`. When a defect surfaces
  later in reviewed code, record it with `review_log.py escape`. Run
  `review_log.py reconcile` (flagged lines that changed since the review
  become `likely-addressed`) and then `review_log.py summary`. The ledger
  stays local because it holds private paths and code lines.

### 7. Report

Severity-ordered, provenance-tagged findings; state the PoC caveat; name
any files the stripper could not process. In sidecar mode: one line
("blind-review sidecar: N blind-only, M divergence: logged").

## Known PoC limitations (disclose when relevant)

- Identifier names still bias the blind pass (`sanitize_input` suggests
  its purpose).
- Stripping is a parse: each language in `LANGUAGES_BY_SUFFIX`,
  `LANGUAGES_BY_NAME`, and `LANGUAGES_BY_GLOB` (`strip_context.py`) uses
  a tree-sitter grammar pinned in the script header, and its comment nodes
  and docstring nodes are blanked. Embedded `<script>` and `<style>`
  bodies, Svelte and Vue template expressions, C macro bodies, and Make
  recipes are parsed with their own grammar. Line-oriented config formats
  (INI, `.properties`, `.gitignore`, `requirements.txt`, `.env`, `go.mod`)
  have no grammar and use their full-line comment rule. Comments that
  change behavior stay: shebangs, `//go:build`, cgo preambles, Go
  `// Output:`, PEP 723 metadata, Ruby magic comments, TypeScript
  `/// <reference>`, `// swift-tools-version:`, MySQL `/*! */` and `/*+ */`,
  and Dockerfile parser directives. A file the grammar cannot parse is
  `copied-verbatim (parse error)`. Pinned grammars reject some valid code:
  dialect SQL (Postgres `DO` blocks, T-SQL `[ids]`), Swift regex literals,
  Groovy slashy strings, and JSON5. Every strip is also checked against a
  space-mask contract (same length, same line count, only blanking) and,
  for Python, against `compile()`. Known silent gaps: strings inside F#
  comments, HTML `<!-->`, `doc` inside Rust `cfg_attr`, and comments in Vue
  directive attributes.
- Only languages with a pinned grammar are stripped. Anything else (for
  example R, Erlang, Clojure, Emacs Lisp, fish, Justfiles, Sass, Solidity,
  Visual Basic, MATLAB, or assembly) is flagged
  `copied-verbatim (unknown language)`, which means its comments reach
  the blind arm: check the manifest before trusting a run whose diff is
  mostly unsupported files.
- Blind isolation is prompt-level, not sandbox-level, except with
  `--mechanical`: there the reviewer process has no tools and receives only
  the unit text. The CLI still adds harness text that this skill cannot
  remove: a billing header with the CLI version, one SDK identity line, an
  account-email note, and an environment block (fixed cwd, platform, OS
  version, model, date, and sometimes a `<total_tokens>` line). Removing it
  needs `--bare` and an API key.
- `--mechanical` output is not deterministic: the CLI sends no temperature
  and uses adaptive thinking, and no flag changes either. Measure stability
  with `bench.py` reps; do not treat one run as the answer.
- `--mechanical` limits: per-file units cannot see cross-file effects or
  unchanged code that a change depends on; the whitespace comparison treats
  any run of spaces as one space, so a change in run length inside a string
  literal is hidden (leading indentation still counts in Python, YAML, and
  Makefiles, and adding or removing a space between tokens always counts).
  Blank lines are skipped, so adding or removing one inside a heredoc or a
  multi-line string is hidden too.
- Scope bundling: the context arm has comments AND repo-wide tools
  (grep, history, other files), so blind-vs-context differences measure
  "does more information of any kind help", not purely comment bias. The
  clean causal claim needs a third arm (full files, no comments, no
  repo-wide tools): not built yet; don't overclaim.
- Diff-length asymmetry: stripped files are shorter; less to read is its
  own advantage independent of de-biasing.
- The merge pass does free-text matching of findings across arms:
  mismatches inflate [blind-only]/[context-only]. Hand-check its matches
  on early runs.
- Single runs are noise: model nondeterminism means a finding appearing
  in one arm once is weak evidence. For measurement use ≥3 repetitions
  per arm and analyze as paired binary outcomes per trap.
