---
name: supply-chain-guidelines
description: Use when auditing third-party dependencies for known vulnerabilities, malicious packages, license or pinning problems across pip, cargo, npm, and Go ecosystems.
---

# Supply Chain Guidelines

Rubric for dependency and supply-chain audits across the ecosystems in use: pip (uv), cargo, npm/pnpm, Go modules.

## Source Of Truth

- OSV database (via `osv-scanner`) as the cross-ecosystem baseline; ecosystem-native auditors for depth
- Lockfiles as the audit target — auditing manifests without lockfiles reports what *could* resolve, not what *is* deployed

## Core Rubric

- Audit the lockfile: `osv-scanner --lockfile=...`, `cargo audit` (Cargo.lock), `pip-audit`, `npm audit`, `govulncheck ./...`. A repo with no committed lockfile is itself a finding.
- **Reachability over presence** — a vulnerable transitive dep whose vulnerable function is never called is a hardening note. `govulncheck` does this natively; elsewhere, state the assumption.
- **Freshness signal** — flag dependencies pinned to exact versions with a comment explaining why (intentional pin) versus stale pins with no rationale. Unexplained exact pins and floating `latest`-style tags both deserve scrutiny.
- **Typosquat / ownership signals** — new transitive deps with low download counts, recent maintainer handover, install-time scripts (`postinstall`, build.rs network fetches) get called out even with no CVE.
- **Container images** — `trivy image` for deployed images; unpinned base image tags are a finding.

## Severity Adjustment

Adjust CVSS by deployment context: a critical RCE in a build-only dev dependency ranks below a medium authz flaw in a runtime request-path library. State the original CVSS and the adjusted rank with the reason.

## Output Contract

A table of actionable advisories (package, installed version, fixed version, ID, adjusted severity, reachability note), then a hygiene section (missing lockfiles, unpinned bases, install scripts), then the exact commands run. Never recommend a blind `upgrade everything` — name the minimal version bump per advisory.
