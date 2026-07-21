---
name: java-guidelines
description: Use when writing or reviewing idiomatic Java — immutability, records, Optional, generics, error handling, and concurrency.
---

# Java Guidelines

Shared Java rubric for agents. Prefer repo-local conventions (build tool, Java version, framework) when deliberate; push back on null-happy APIs, raw types, and inheritance where composition fits.

## Source Of Truth

- *Effective Java* (Bloch) and the Google Java Style Guide
- The repo's `pom.xml`/`build.gradle`, target Java release, and static-analysis config (ErrorProne, SpotBugs, Checkstyle)

## Core Rubric

- Immutability first: `record` for data carriers (Java 16+), `final` fields, defensive copies of mutable inputs. Make classes immutable unless there's a reason not to.
- `Optional` as a return type for "might be absent" — never as a field or parameter, never `.get()` without `isPresent`/`orElse`.
- Program to interfaces; prefer composition over inheritance; design and document for inheritance or forbid it (`final`/sealed).
- `sealed` classes/interfaces for ADTs (Java 17+) with exhaustive `switch` patterns.
- Generics: no raw types, no unchecked-warning suppression without a `@SuppressWarnings` justified by comment; use bounded wildcards (PECS) for flexible APIs.
- `equals`/`hashCode` together and consistent; `toString` for debuggable types.
- Resources via try-with-resources; never swallow exceptions; throw specific types; don't use exceptions for control flow.
- Streams where they clarify, loops where they're plainer — don't force a one-liner stream that hides intent or allocates needlessly.
- Concurrency: prefer `java.util.concurrent` and immutable shared state over `synchronized` hand-rolling; document thread-safety; avoid leaking `this` during construction.

## Verification

Run the repo gates: `./gradlew spotlessCheck` / `mvn spotless:check`, the static-analysis tasks (ErrorProne/SpotBugs/Checkstyle), and `./gradlew test` / `mvn test` (JUnit 5).

## Output Contract

When reviewing, lead with severity-ranked findings and file/line evidence: correctness > resource/thread safety > API design > performance > style. When implementing, make the smallest coherent change, add tests for observable behavior, and record the exact proof command.
