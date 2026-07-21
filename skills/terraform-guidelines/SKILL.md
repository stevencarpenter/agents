---
name: terraform-guidelines
description: Use when writing or reviewing Terraform/OpenTofu — module structure, state, provider/version pinning, variable validation, security, and plan hygiene.
---

# Terraform Guidelines

Shared Terraform/OpenTofu rubric for agents. Prefer repo-local conventions (module layout, state backend, naming) when deliberate; push back on hardcoded secrets, unpinned providers, and `count`-indexed resources that churn on reorder.

## Source Of Truth

- HashiCorp's Terraform style conventions and module standards; OpenTofu docs where the repo uses tofu
- The repo's `versions.tf`/backend config and any `tflint`/`checkov`/`tfsec` rules

## Core Rubric

- Standard module layout: `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`. Keep modules small and single-purpose; compose them.
- Pin `required_version` and every provider with a `~>` constraint in `versions.tf`. Don't float providers.
- State: remote backend with locking; never commit state files or `.terraform/`. One state per environment; avoid one monolithic state for everything.
- **Secrets never inline and never in state-visible plaintext.** Pull from a secrets manager / env / `op://`-style references; mark sensitive variables and outputs `sensitive = true`. (This repo's homelab feeds Cloudflare/Tailscale tokens from 1Password, not the tree.)
- Variables: explicit `type`, a `description`, and `validation` blocks for constrained inputs. Outputs documented; expose only what callers need.
- Prefer `for_each` (stable, keyed addressing) over `count` (index churn on insert/remove). Use `data` sources over hardcoded IDs.
- Least-privilege IAM/API scopes; tag/label resources consistently. Avoid `provisioner` blocks (last resort) and `local-exec` side effects.
- `lifecycle` (`prevent_destroy`, `ignore_changes`) only with a stated reason. No `terraform apply` without reviewing the `plan`.

## Verification

Run the repo gates: `terraform fmt -check -recursive` (or `tofu fmt`), `terraform validate`, `tflint`, a security scan (`tfsec`/`checkov`) when configured, and review `terraform plan` output before any apply. Never apply from a dev machine if the repo deploys elsewhere.

## Output Contract

When reviewing, lead with severity-ranked findings and file/line evidence: security/secret exposure > state/correctness > addressing stability (`for_each` vs `count`) > maintainability > style. When implementing, make the smallest coherent change, show the relevant `plan` diff, and record the exact commands run.
