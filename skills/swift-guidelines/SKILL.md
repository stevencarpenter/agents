---
name: swift-guidelines
description: Use when writing or reviewing idiomatic Swift — value types, optionals, protocol-oriented design, error handling, and structured concurrency.
---

# Swift Guidelines

Shared Swift rubric for agents. Prefer repo-local conventions (SwiftPM vs Xcode project, UIKit/SwiftUI, platform) when deliberate; push back on force-unwraps, reference-type-by-default, and retain cycles.

## Source Of Truth

- The Swift API Design Guidelines (swift.org) and the Swift language reference
- The repo's `Package.swift`/Xcode settings, `SwiftLint`/`swift-format` config, and Swift version

## Core Rubric

- Value types by default: `struct`/`enum` over `class` unless you need identity or reference semantics. `let` over `var`.
- Optionals: never force-unwrap (`!`) outside of provably-safe cases with a comment. Use `if let`/`guard let`, `??`, optional chaining. `guard` for early exit to keep the happy path unindented.
- `enum` with associated values for state machines and modeling; exhaustive `switch` (avoid `default` when cases are known).
- Use concrete types by default. Add a small protocol for an actual shared contract or interchangeable behavior; prefer composition over class inheritance.
- Errors: `throws`/`Result` for recoverable failures; don't use optionals to hide error causes. Name per the API Design Guidelines (clarity at the call site, omit needless words).
- Memory: break retain cycles with `[weak self]`/`[unowned self]` in escaping closures; understand value-vs-reference capture.
- Concurrency: `async`/`await` over completion handlers; structured concurrency (`async let`, task groups); `actor` for shared mutable state; respect `Sendable`; don't block the main actor.
- `Codable` for serialization; avoid manual JSON parsing.

## Verification

Run the repository's configured formatting and relevant SwiftPM or Xcode scheme tests. Use SwiftLint, swift-format, XCTest, or Swift Testing as configured; do not add tools or convert the test framework for unrelated work.

## Output Contract

When reviewing, lead with severity-ranked findings and file/line evidence: correctness > memory/concurrency safety > API clarity > performance > style. When implementing, make the smallest coherent change, add tests for observable behavior, and record the exact proof command.
