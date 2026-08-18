---
name: security-review-guidelines
description: Use when reviewing any code, config, or diff for security weaknesses — authentication, authorization, injection, SSRF, secrets handling, crypto misuse — regardless of language.
---

# Security Review Guidelines

Shared security rubric for agents. Language rubrics (python-guidelines, rust-guidelines, ...) govern idiom; this rubric governs exploitability. When they conflict, security wins.

## Source Of Truth

- OWASP ASVS (verification requirements) and OWASP Top 10 (2021) for web/API flaws
- CWE identifiers for classification — cite the CWE, not just a vibe
- The repo's own authz/authn design docs, when present — understand intended trust boundaries before flagging their violation

## Core Rubric

Review in attacker order — what an unauthenticated remote party can reach first:

1. **Authn/session** — JWT verification (algorithm confusion, missing expiry/audience/issuer checks, untrusted `kid`), session fixation, weak password reset, missing webhook signature verification.
2. **Authz** — IDOR/BOLA (object access scoped to caller, not just authenticated), missing function-level checks, privilege escalation via mass assignment.
3. **Injection** — SQL (string-built queries outside the ORM's parameterized path), OS command (`shell=True`, unsanitized argv), template/SSTI, header injection, log injection.
4. **SSRF & outbound calls** — user-influenced URLs in server-side fetchers, redirects followed across origins, cloud metadata endpoints reachable.
5. **Data exposure** — secrets in logs/errors/repos, overly broad CORS, stack traces in prod responses, presigned URLs with excessive scope or lifetime.
6. **Crypto** — hand-rolled constructions, weak algorithms (MD5/SHA1/ECB), predictable randomness for security tokens, missing zeroization of key material.
7. **Configuration** — debug modes, default credentials, fail-open error paths (`except: allow`), permissive container/infra defaults.

## Evidence Standard

Every finding must carry: severity (critical/high/medium/low), CWE, file:line, the concrete attacker path, and why it is reachable. A finding without a reachable path is a hardening note — label it as such, never inflate it.

## False-Positive Discipline

Before reporting, attempt to falsify the finding: trace sanitization upstream, check framework defaults (e.g. an ORM parameterizes by default), confirm the input is actually attacker-controlled. Report residual doubt explicitly rather than dropping the finding silently.

## Output Contract

Severity-ranked findings, each with CWE, file:line evidence, attacker path, and the minimal fix direction. Close with residual risk: what was not reviewed (dynamic behavior, dependencies, infra) and which specialist should cover it (sast-scanner, dependency-auditor, staging-pentester).
