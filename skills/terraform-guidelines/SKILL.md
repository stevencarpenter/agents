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

- Follow the existing module layout. Split files or extract modules when responsibilities or real reuse warrant it; a small configuration can remain in one file.
- Declare compatible Terraform/provider version constraints and preserve the dependency lockfile. Match root-module pinning and reusable-module compatibility policy; do not force `~>` everywhere.
- State: preserve the configured backend, locking, and environment isolation. Use a shared backend when collaborating or deploying through automation; do not provision one for an isolated local example. Never commit state files or `.terraform/`.
- Keep secrets out of source and logs. `sensitive = true` redacts display but does not exclude values from state, even when supplied by a secrets manager. Use supported ephemeral/write-only inputs or manage the secret value outside Terraform when it must stay out of state; protect state access and encryption ([sensitive data](https://developer.hashicorp.com/terraform/language/manage-sensitive-data)).
- Variables: explicit `type`, a `description`, and `validation` blocks for constrained inputs. Outputs documented; expose only what callers need.
- Prefer `for_each` (stable, keyed addressing) over `count` (index churn on insert/remove). Use `data` sources over hardcoded IDs.
- Least-privilege IAM/API scopes; tag/label resources consistently. Avoid `provisioner` blocks (last resort) and `local-exec` side effects.
- `lifecycle` (`prevent_destroy`, `ignore_changes`) only with a stated reason. No `terraform apply` without reviewing the `plan`.

## Verification

Run the repository's configured Terraform/OpenTofu formatting, validation, and relevant analysis. Review the plan before an authorized apply; do not install tflint or a security scanner for unrelated work. Never apply from a dev machine if the repo deploys elsewhere.

## Output Contract

When reviewing, lead with severity-ranked findings and file/line evidence: security/secret exposure > state/correctness > addressing stability (`for_each` vs `count`) > maintainability > style. When implementing, make the smallest coherent change, show the relevant `plan` diff, and record the exact commands run.
