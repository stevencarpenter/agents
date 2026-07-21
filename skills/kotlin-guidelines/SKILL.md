---
name: kotlin-guidelines
description: Use when writing or reviewing idiomatic Kotlin — null safety, immutability, data/sealed classes, coroutines, and scope functions.
---

# Kotlin Guidelines

Shared Kotlin rubric for agents. Prefer repo-local conventions (build setup, coroutine vs Rx, Android vs server) when deliberate; push back on `!!`, platform-type leaks, and gratuitous scope-function nesting.

## Source Of Truth

- Kotlin coding conventions (kotlinlang.org) and *Effective Kotlin* (Moskała)
- The repo's Gradle (Kotlin DSL) config, `detekt`/`ktlint` rules, and target (JVM/Android/Multiplatform)

## Core Rubric

- `val` over `var`; immutable collections (`listOf`, `mapOf`) unless mutation is required; expose read-only types in public APIs.
- Null safety: never `!!`. Use `?.`, `?:`, `let`/`also`, and smart casts. Guard platform types coming from Java at the boundary — don't let them propagate untyped.
- `data class` for value types; `sealed class`/`sealed interface` for ADTs with exhaustive `when` (no `else` branch when it can be exhaustive).
- Prefer expressions (`if`/`when`/`try` as values) and single-expression functions where they read clearly.
- Extension functions to extend types you don't own — but keep them discoverable and cohesive, not a junk drawer.
- Coroutines: structured concurrency only — no `GlobalScope`; pass a `CoroutineScope`/use `coroutineScope {}`; pick the right `Dispatcher`; make suspend functions main-safe; don't block inside `suspend`.
- Scope functions (`let`/`run`/`with`/`apply`/`also`) used for their intent, not stacked into unreadable chains.
- Preconditions with `require`/`check`/`error`; results with sealed `Result`-style types or `Result<T>`, not swallowed exceptions.

## Verification

Run the repo gates: `./gradlew ktlintCheck` (or `ktfmt`), `./gradlew detekt`, and `./gradlew test` (JUnit5 or Kotest).

## Output Contract

When reviewing, lead with severity-ranked findings and file/line evidence: correctness > null/coroutine safety > API design > performance > style. When implementing, make the smallest coherent change, add tests for observable behavior, and record the exact proof command.
