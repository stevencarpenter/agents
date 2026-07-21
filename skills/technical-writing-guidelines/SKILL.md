---
name: technical-writing-guidelines
description: Use when writing or reviewing any technical document — choosing the right Diátaxis mode (tutorial, how-to, reference, explanation), keeping the modes from bleeding into each other, and meeting the quality bar for the mode you are in. Shared rubric for documentation-writer, technical-writer, and any agent producing prose for people to read.
---

# Technical Writing Guidelines

The Diátaxis rubric (after Daniele Procida). Shared across the writing agents. Decide which kind of document you are writing *before* you draft, then stay in it. Diagrams follow `diagramming-guidelines` (Figma-first), not this file.

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

If a single request spans modes, write each piece separately and link them. Reference work belongs to `documentation-writer`; the other three belong to `technical-writer`. One deliberate exception: in-repo decision records (ADRs) are explanatory by nature but stay with `documentation-writer` — they live beside the code as durable reference material, so the agent that owns the repo's reference layer owns them.

## The cardinal rule: do not mix modes

This is the whole point of Diátaxis. Mixing is the most common failure:

- A tutorial that pauses to explain alternatives stops being learnable — the beginner loses the thread.
- A how-to clogged with background stops being usable — the competent reader can't scan to the step.
- Reference that teaches stops being trustworthy as a lookup.
- Explanation broken into numbered steps stops explaining.

When you catch yourself adding the wrong mode's content, cut it and link to the page that owns it.

## Per-mode quality bars

**Tutorial** — runs end to end from a clean state; versions pinned; every step and its expected output verified; a visible win in the first few minutes; one path only, no "you could also".

**How-to** — title is the goal in the reader's words ("Back up Postgres to S3"); opens with prerequisites, closes with verification ("you should now see…"); one task per guide; link out instead of inlining a second task. Every state-changing step pairs its success check with a recovery line — what the reader does *if this step fails or looks wrong* — not just a description of success.

**Reference** — accurate above all; structured for scanning, not reading; documents inputs, outputs, and error conditions, not implementation; consistent layout across entries; deprecations carry a migration path. (Owned by `documentation-writer`.)

**Explanation** — leads with the why; surfaces the alternatives that were rejected and *why-not* (the highest-value, hardest-to-find content); admits trade-offs; makes no promise to be exhaustive. Anchor the central abstraction in one small inspectable artifact or worked example threaded through the piece (a four-line event log, a sample payload, one recurring scenario) — five disconnected hypotheticals are weaker than one the reader can follow end to end.

## Every doc needs a why

Explanation is the most-skipped mode. Most prompts and docs are all How-to and Reference with no rationale, so readers (and future maintainers) can't tell a deliberate choice from an accident. Even a reference-heavy doc should link to one explanation of the design's intent. When reviewing, if you can't find the *why*, that's the gap.

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
- Keep the honest-caveats section, but limit it strictly to *reader-relevant unverified factual claims* (commands not executed, versions not checked). Process notes ("diagram to be created later when Figma is reachable") belong in the surrounding delivery message, not the document.

## Output contract

For anything non-trivial, first state the mode, the audience, the one-sentence outcome, and a section outline; get agreement; then write. That planning statement lives in the conversation — it never appears inside the finished document. Deliver the draft, the runnable examples, any FigJam diagram per `diagramming-guidelines`, and an explicit list of what you could not verify (reader-relevant claims only, clearly separated from the document body).
