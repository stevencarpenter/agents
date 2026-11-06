---
name: re-provenance-guidelines
description: Use when turning reverse-engineering findings into original code, physics models, graphics pipelines, or specifications, so every constant carries a provenance label and no game value is presented as a measurement.
---

# Provenance Guidelines for Reconstructed Systems

Shared rubric for code built from reverse-engineering findings. A finding describes what a
shipped build does. A port is original code that chooses what to keep. The labels below keep
the two apart in code, tests, and documents.

## Labels

| Label | Meaning | Example |
|---|---|---|
| **Observed** | Read from the shipped binary or shipped tables, with an address or a digest | `SNOW_DIVISOR = 2.5  // Observed, FINDINGS 49.2` |
| **Verified** | Observed and re-read at instruction level in a verification pass | `SLIP_EXPONENT = 0.75  // Verified, FINDINGS 48` |
| **Inferred** | Consistent with observed code, not confirmed by a named field or a test | always named as such, never promoted silently |
| **Derived** | Computed from observed values | `CELL_M = 24.5 / 49  // Derived` |
| **Tunable** | A modelling choice in a reference model, not a measurement | `STEP_GAIN` in a registry, never in a finding |
| **Design** | A choice made here. Game tuning copied as a starting point is `Design, from <game>` | `REPOSE_DEG = 40.0  // Design, from Roadcraft findings/roadcraft-terraforming-tools.md` |
| **Spec** | A catalogue or data-sheet value recalled from memory, not checked | treat as Design until cited |

Rules:

1. Label every physical or behavioural constant in code, and cite the source in the same
   comment. A reviewer rejects an unlabelled constant.
2. Never present a Tunable, Design, or Spec value as the game's behaviour or as a measurement
   of the real world. A game value is tuning.
3. Expose every open item as a named parameter with the documented default. Do not bury an
   open item inside a literal.
4. Reference models keep three registries (OBSERVED, DERIVED, TUNABLES). A self-check fails
   when a module constant is in none or in more than one.

## Precedence when sources disagree

Highest first: errata tables read from the listing; the ledger of record; derived
specifications; a reference model's OBSERVED and DERIVED registries; design notes. Nothing in
design notes is a finding, and no finding lives only in design notes.

## Porting rules

- Implement from the specification and the ledger. Read disassembly only to close an open item.
- Port absence explicitly. If the game has no decay, no lateral transport, or no collision on a
  render-only mesh, write that down as a decision, either kept (fidelity) or exceeded (Design).
- Do not port a known defect (mass lost at a cell ceiling, a coarse quantum, an ignored return
  value) unless the fidelity tier requires it. Name the defect and the choice.
- Keep units and coordinate frames explicit and convert at one boundary (for example, a physics
  engine in centimetres against a simulation in metres).
- Never copy decompiled code, shaders, scripts, or assets. Describe the behaviour, then write it
  in the target language with its own idioms. Shipped data files stay read-only and byte-exact
  when they are vendored as evidence.
- Keep the target codebase's rules: where the simulation lives, which layer owns rendering,
  which files are generated and must not be hand-edited.

## Fidelity tiers and tests

- **Tier 1, exact.** Grid sizes, texel encodings, gate order, clamp bounds. Test with values
  from shipped data.
- **Tier 2, behavioural.** Monotonic ramps, no overshoot, clamped borders, conservation. Test
  with properties.
- **Tier 3, design.** Depth scales, storage format, relaxation. Test against the design, and say
  so.

Use the reference model as the test oracle, with a per-output table that states whether a
match is required (Observed) or not (Tunable, Design). Name acceptance tests (T1, T6c) in both
the specification and the code.

## Citing and vendoring

- Cite `FINDINGS <section>`, `SPEC/<doc> section <n>`, `findings/<file>`, or
  `evidence/<dir>/<file>` in code comments and commit messages.
- Vendor a findings package under `docs/research/<package>/` with `SHA256SUMS` and the source
  commit. Rename the package's `AGENTS.md` to `AGENTS.source.md` and drop its `CLAUDE.md`, so
  the consumer repository does not load the package's instructions.
- Read the errata before the documents they correct. Keep an "errata precedence" line at the
  top of any derived document.

## Builder check

Before a specification is handed over, a fresh reader checks every claim it makes about the
consumer codebase against the code. One such check found six wrong claims in a 900-line
specification. Fold the answers back in and list the calls the author made.

## Output contract

When implementing, report the files changed, the labels used, each open item exposed as a
parameter, and the exact proof command. When reviewing, lead with unlabelled or mislabelled
constants, then inferences presented as findings, then defects ported without a decision.
