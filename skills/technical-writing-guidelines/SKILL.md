---
name: technical-writing-guidelines
description: Use when writing or reviewing technical documentation whose reader goals, instructions, examples, or explanatory structure need attention. Shared rubric for documentation-writer and technical-writer.
---

# Technical Writing Guidelines

Use Diátaxis (after Daniele Procida) to identify the reader's primary need. Preserve a useful existing document structure; an ordinary edit does not require reclassifying or splitting the whole document. Apply `diagramming-guidelines` when a diagram helps.

## The two axes, four modes

Documentation serves two independent needs — **action vs cognition** (doing something vs thinking about something) and **study vs work** (acquiring skill vs applying it). That gives four modes, and each serves a different reader:

| Mode | Reader need | Axis | Reads like |
|------|-------------|------|-----------|
| **Tutorial** | learning by doing | study + action | a lesson — hand-held, guaranteed to succeed |
| **How-to guide** | completing a task | work + action | a recipe — goal-directed, assumes competence |
| **Reference** | looking something up | work + cognition | a map — dry, exhaustive, accurate |
| **Explanation** | understanding | study + cognition | a discussion — context, trade-offs, the why-not |

## Detect the mode

Ask what the reader is doing when they reach for the page:

- "I'm new and want to get started" → **Tutorial**
- "I know what I want, show me the steps" → **How-to**
- "I need the exact signature / flag / field" → **Reference**
- "I want to understand why it works this way" → **Explanation**

Separate substantial material for different reader tasks when that improves navigation; a short explanation or example can stay beside the operation it clarifies. Reference work and in-repo ADRs belong to `documentation-writer`; tutorials, how-tos, and explanations belong to `technical-writer`.

## Keep the reader's task clear

Avoid unrelated material that interrupts the reader:

- A tutorial that pauses to explain alternatives stops being learnable — the beginner loses the thread.
- A how-to clogged with background stops being usable — the competent reader can't scan to the step.
- Reference should make signatures, constraints, and examples easy to find.
- Explanation can include a short sequence when order is what it explains.

Move a substantial digression to an existing relevant page; do not create a new document merely to enforce a taxonomy.

## Per-mode quality bars

**Tutorial** — runs end to end from a clean state; versions pinned; every step and its expected output verified; a visible win in the first few minutes; one path only, no "you could also".

**How-to**: title states the goal; include prerequisites and a success check. Add recovery instructions for state changes whose failure can leave the reader stuck or lose data. Routine reversible commands do not each need a rollback paragraph.

**Reference** — accurate above all; structured for scanning, not reading; documents inputs, outputs, and error conditions, not implementation; consistent layout across entries; deprecations carry a migration path. (Owned by `documentation-writer`.)

**Explanation** — leads with the why; surfaces the alternatives that were rejected and *why-not* (the highest-value, hardest-to-find content); admits trade-offs; makes no promise to be exhaustive. Anchor the central abstraction in one small inspectable artifact or worked example threaded through the piece (a four-line event log, a sample payload, one recurring scenario) — five disconnected hypotheticals are weaker than one the reader can follow end to end.

## Explain consequential choices

Include or link rationale when it affects the reader's decision or safe use. A flag reference or small procedural edit does not require a separate design explanation.

## Voice and mechanics

- Active voice, present tense, second person. Short sentences.
- Cut "simply", "just", "easy", "obviously", "note that", and adjectives that carry no information. If a sentence survives deletion without loss, delete it.
- Prose for explanation; lists for steps, options, and parameters.
- Define each term once on first use, then use it consistently. Never two names for one thing.

## Docs-as-code

- Treat examples as tested code — run them in CI where possible, by hand otherwise, before publishing.
- Version docs with the thing they describe; flag version-specific behavior.
- Check links; regenerate screenshots when the UI changes; never ship a stale screenshot.

## The deliverable is the document, not a report about it

The reader of the finished piece must never see your process. Author-to-reader meta-narration is a Diátaxis violation in its own right:

- No mode/audience/outcome labels inside the document ("Mode: How-to (Diátaxis). Audience: …"). Those are planning coordination — they go in a message *around* the deliverable, never in it.
- The document opens with its own title and goal line, and ends when the content ends.
- No process or tooling narration in the artifact: never mention that a tool/MCP was unavailable, name internal guideline files, or justify your own scope choices ("an explanation shouldn't have runnable steps, so…").
- State reader-relevant uncertainty where it affects use. Do not append a caveat section unless needed; process notes belong in the delivery message.

## Output contract

Deliver the requested document or edit with verified examples where relevant. Ask for clarification only when a missing audience, scope, or constraint changes the result; do not require outline approval for work already authorized. State material verification gaps in the delivery message.
