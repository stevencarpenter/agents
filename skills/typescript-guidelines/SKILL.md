---
name: typescript-guidelines
description: Use when writing, reviewing, or designing TypeScript or JavaScript where strict typing, async correctness, null safety, or runtime-target concerns matter.
---

# TypeScript Guidelines

Shared TypeScript/JavaScript rubric for agents. Prefer repo-local conventions (import style, runtime, path aliases) when deliberate; push back when they defeat the type system or hide async bugs.

## Source Of Truth

- The repo's `tsconfig.json` — `strict` and its sub-flags are the contract
- TypeScript handbook for language semantics; the runtime's docs (Node, Bun, edge, browser) for platform APIs

## Core Rubric

- Compile clean under `strict`. Honor `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes` when enabled.
- No `any`. Use `unknown` for genuinely unknown values and narrow with guards. Never use `as` to silence a type error; reserve casts for cases the compiler provably can't see, with a comment.
- No `@ts-ignore` / `@ts-expect-error` without a cited reason.
- `type` for unions/computed shapes; `interface` for shapes meant to be extended. `const` by default; `let` only when mutation is required.
- Async: explicit `Promise<T>` return types; never leave floating promises; always `await` inside `try/catch`; no async work in constructors. Don't swallow rejections with empty `.catch()`.
- Null safety: don't paper over `undefined` with optional chaining where downstream code assumes a value. Justify every non-null assertion (`!`).
- Errors: throw typed error classes or return a `Result<T, E>` shape — never silently return `undefined` on failure.
- React: function components + hooks; explicit prop types; `useEffect` that opens a connection/subscription must return a cleanup.

## Security & Runtime

- No `innerHTML` / `dangerouslySetInnerHTML` with user content. Validate `JSON.parse` output before trusting it.
- Don't mix runtime targets: no Node-only APIs in browser/edge bundles; watch `import.meta.env` leakage; no sync filesystem calls in an async server path.

## Verification

Run `tsc --noEmit` (or `bun tsc --noEmit`), then the repo's test runner (`vitest run`, `bun test`, `npm test`), then `eslint .` if configured.

## Output Contract

When reviewing, lead with severity-ranked findings with file/line evidence: type holes > async correctness > null safety > security > runtime mismatch > bundle > style. When implementing, make the smallest coherent change, add tests for observable behavior, and record the exact proof command.
