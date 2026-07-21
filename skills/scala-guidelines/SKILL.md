---
name: scala-guidelines
description: Use when writing or reviewing idiomatic Scala — functional design, immutability, ADTs, type classes, effect systems, and collection performance.
---

# Scala Guidelines

Shared Scala rubric for agents. Prefer repo-local conventions (Scala 2 vs 3, effect library) when deliberate; push back when code reaches for nulls, exceptions-as-control-flow, or implicit magic.

## Source Of Truth

- Scala 3 (Dotty) reference and the official style guide
- *Effective Scala* (Twitter); the cats / ZIO docs when the repo uses an effect system
- The repo's `build.sbt`/`build.mill` and compiler flags (`-Xfatal-warnings`, `-Wunused`) — these are the contract

## Core Rubric

- `val` and immutable collections by default; `var` never in a public API. Prefer pure functions and referential transparency.
- Model data with `case class` and sealed-trait/`enum` ADTs; exhaust pattern matches (let `-Xfatal-warnings` catch the rest).
- `Option`/`Either`/`Try` over `null` and over throwing for expected failures. Reserve exceptions for truly exceptional cases.
- Pattern matching and `for`-comprehensions over nested `flatMap`/`isInstanceOf`/`asInstanceOf`.
- Scala 3: `given`/`using` for type classes; Scala 2: implicit instances scoped narrowly. Don't smuggle behavior through broad implicit conversions.
- Effects: if the repo uses cats-effect or ZIO, keep effects in `IO`/`F[_]` to the edges; don't run effects in constructors or block inside them. Tagless-final only when it buys real abstraction.
- Collections: know strict vs lazy (`View`, `LazyList`); avoid O(n) `head`/`apply` on `List`; pick the structure that matches the access pattern.
- Keep type signatures legible — name complex types, avoid gratuitous higher-kinded gymnastics.

## Verification

Run the repo gates: `sbt scalafmtCheckAll`, `sbt "scalafixAll --check"`, compile with `-Xfatal-warnings`, and `sbt test` (ScalaTest or MUnit — match the repo).

## Output Contract

When reviewing, lead with severity-ranked findings and file/line evidence: correctness > effect/resource safety > type clarity > performance > style. When implementing, make the smallest coherent change, add tests for observable behavior, and record the exact proof command.
