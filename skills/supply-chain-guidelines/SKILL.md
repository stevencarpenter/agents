---
name: supply-chain-guidelines
description: Use when auditing third-party dependencies for known vulnerabilities, malicious packages, license or pinning problems across pip, cargo, npm, and Go ecosystems.
---

# Supply Chain Guidelines

Rubric for dependency and supply-chain audits across the ecosystems in use: pip (uv), cargo, npm/pnpm, Go modules.

## Source Of Truth

- The repository's configured advisory scanner and dependency policy; add a second scanner only for a relevant coverage gap.
- Lockfiles as the audit target — auditing manifests without lockfiles reports what *could* resolve, not what *is* deployed

## Core Rubric

- Audit resolved dependencies with an appropriate configured tool, such as `osv-scanner`, `cargo audit`, `pip-audit`, `npm audit`, or `govulncheck`. Assess missing lockfiles against the ecosystem and whether the artifact is a deployed application or a reusable library; do not flag absence without that context.
- **Reachability over presence** — a vulnerable transitive dep whose vulnerable function is never called is a hardening note. `govulncheck` does this natively; elsewhere, state the assumption.
- **Freshness signal** — flag dependencies pinned to exact versions with a comment explaining why (intentional pin) versus stale pins with no rationale. Unexplained exact pins and floating `latest`-style tags both deserve scrutiny.
- **Typosquat / ownership signals**: investigate unexpected ownership changes, suspicious names, and install-time network or credential access. Low download counts or the existence of an install script alone do not establish a vulnerability.
- **Container images** — `trivy image` for deployed images; unpinned base image tags are a finding.

## Severity Adjustment

Adjust severity by reachable behavior and execution privileges. A build dependency can access release credentials or alter shipped artifacts; do not automatically downgrade it. State the original advisory severity and any adjustment with evidence.

## Output Contract

A table of actionable advisories (package, installed version, fixed version, ID, adjusted severity, reachability note), then a hygiene section (missing lockfiles, unpinned bases, install scripts), then the exact commands run. Never recommend a blind `upgrade everything` — name the minimal version bump per advisory.
