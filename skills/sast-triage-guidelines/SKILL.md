---
name: sast-triage-guidelines
description: Use when running or triaging static analysis (Semgrep, Bandit, gosec, cargo-audit, language linters) and turning raw scanner output into verified, severity-ranked findings.
---

# SAST Triage Guidelines

Rubric for running static analyzers and converting noisy output into trustworthy findings.

## Source Of Truth

- Semgrep registry rulesets (`p/default`, `p/security-audit`, `p/owasp-top-ten`) as the baseline; per-language tools for depth
- The repo's existing lint/SAST config — run it first, it encodes accepted suppressions

## Tool Selection By Stack

- Multi-language sweep: `semgrep scan --config auto` (or pinned registry packs) with `--sarif` for machine-readable output
- Python: `bandit -r .`, `ruff check --select S .`
- Go: `gosec ./...`, `govulncheck ./...` (call-graph reachability, not just imports)
- Rust: `cargo audit`; clippy correctness lints already gate in most repos here
- TypeScript/JS: `npm audit` is dependency-only — pair with semgrep `p/javascript` + `p/react`
- Infra: `trivy config .`, `checkov -d .` for Terraform, `hadolint` for Dockerfiles

## Triage Protocol

1. **Dedupe** by (rule, file, line) before reading anything.
2. **Verify reachability** — is the flagged sink reachable from attacker-controlled input? Read the actual code path; scanner dataflow is best-effort.
3. **Falsify** — try to construct the reason the finding is wrong (sanitizer upstream, framework default, test-only code). A falsified finding is recorded as dismissed-with-reason, not silently dropped.
4. **Rank** by exploitability in this deployment, not by the scanner's generic severity. A SQLi in a dead admin route ranks below a reflected XSS on the login page.
5. **Group** repeated instances of one weakness class into a single finding with a file list — never paste 40 near-identical rows.

## Custom Rules

When a weakness is repo-specific (internal auth helper misused, project-specific sink), write a Semgrep rule for it rather than flagging instances by hand — rules persist, findings rot. Test the rule against a known-bad and a known-good snippet before trusting its output.

## Output Contract

Verified findings only, severity-ranked, each with rule ID, CWE, file:line, and the falsification attempt that failed. Append a dismissed section (rule ID + count + one-line reason) so the reader can audit triage judgment. Name the exact commands run.
