---
name: dast-staging-guidelines
description: Use when dynamically testing a deployed staging environment — OWASP ZAP, Nuclei, TLS checks, targeted probes — under explicit rules of engagement and scope.
---

# DAST Staging Guidelines

Rules of engagement (ROE) and methodology for dynamic testing of deployed staging environments. This rubric is a hard gate: an agent that cannot satisfy the authorization gate must stop and ask.

## Authorization Gate (Mandatory)

Before sending a single probe, all of the following must hold:

1. The target URL was given explicitly by the operator, or appears in the operator-approved scope list in the task prompt.
2. The target is a staging/preview environment — never production. Production hostnames end the run unless the operator re-confirms in writing.
3. Credentials, if used, were supplied by the operator for this engagement.

If any condition fails, stop and ask. No silent escalation, no expanding scope to "interesting" sibling hosts.

## Methodology (Passive First, Escalate Slowly)

1. **Fingerprint passively** — response headers, TLS (`testssl.sh` or `curl -sv`), framework fingerprints. Zero active probing.
2. **Baseline scan** — OWASP ZAP baseline (`zap-baseline.py`) or `nuclei -tags exposure,misconfig` at low rate. No fuzzing yet.
3. **Map the surface** — crawl routes, enumerate API endpoints from OpenAPI specs if exposed, note auth boundaries.
4. **Targeted probes** — only where static context suggests weakness: IDOR on object IDs, authz across roles, known-CVE templates from `nuclei` matched to fingerprinted versions.
5. **Active fuzzing** (ZAP full scan, sqlmap, ffuf brute force) — only with an explicit operator opt-in for this run, at throttled rates, never against shared infrastructure.

## Constraints

- Throttle: default to <= 5 req/s unless the operator approves higher. Staging shares resources; a scan that takes down staging is a failed engagement.
- No DoS templates, no credential stuffing, no destructive payloads (DELETE/PUT fuzzing) unless explicitly scoped.
- Exfiltrate nothing. Proof of a finding is the minimal request/response pair — redact any real user data encountered and report its presence.
- Authenticated scans get a dedicated throwaway account; never reuse an operator's personal credentials.

## Output Contract

Findings severity-ranked with: the exact request, the (redacted) response evidence, why it is exploitable, and CWE. Separately report: scan coverage (routes hit / routes known), tools + versions + template sets used, and anything blocked by the authorization gate so the operator can widen scope deliberately.
