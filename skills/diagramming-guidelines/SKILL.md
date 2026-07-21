---
name: diagramming-guidelines
description: Use when a document, slide, design, or review needs a diagram — architecture, sequence, flow, ERD, or state. Figma FigJam is the default and preferred tool; this rubric covers the FigJam-via-Figma-MCP workflow, the board-plus-snapshot deliverable, diagram-type selection, and the narrow fallbacks. Shared across technical-writer, slide-designer, data-engineer, and any agent that draws.
---

# Diagramming Guidelines

**Figma FigJam is the house standard for diagrams. Prefer it over every other tool** — Mermaid, Excalidraw, ASCII, draw.io, PlantUML. The Figma MCP, plugin, and skills are strong and getting stronger; the artifact a reader gets should be a real, editable board, not a code block.

## Why FigJam first

A FigJam board is collaborative, live, and durable: it can be opened, restyled, annotated, and extended by anyone, and it embeds cleanly as a high-resolution image. A Mermaid block in a doc is none of those — it is locked to one renderer, hard to lay out deliberately, and fights you the moment a diagram gets non-trivial. Use the tool that produces an asset the team keeps, not a snippet that rots.

## Workflow (Figma MCP)

1. **Load the prerequisite skill first.** `/figma-generate-diagram` is mandatory *before* any `generate_diagram` call; `/figma-create-new-file` before `create_new_file`; `/figma-use-figjam` (and `/figma-use`) before any `use_figma` call. Skipping them causes avoidable failures.
2. **Get a board.** Target an existing FigJam file, or create one (`/figma-create-new-file` → `create_new_file` with editorType `figjam`).
3. **Generate the diagram.** For flowcharts, architecture, sequence, ERD, and state diagrams use `generate_diagram`. It accepts Mermaid-style syntax as *input* and renders a FigJam board from it — so Mermaid may exist transiently as the generation input, but **the board is the published artifact, never a Mermaid code block in the doc.**
4. **Refine richer boards** (swimlanes, grouping, callouts, custom layout) with `use_figma`.
5. **Verify** with `get_figjam` or `get_screenshot` before declaring done.

## Deliverable contract

Every diagram ships as three things:

1. The **editable FigJam board link**.
2. An **exported PNG or SVG snapshot** committed next to the doc/slide and embedded inline.
3. A **prose description** in the surrounding text — for accessibility, for skimmers, and for readers whose render fails.

The published artifact is the board plus snapshot. Do not leave a raw Mermaid/Excalidraw block as the final diagram when Figma is available.

## Diagram-type selection

Match the diagram to the intent; one concept per board:

- **Flowchart** — a process or decision path.
- **Sequence** — interaction between actors over time.
- **Architecture / system** — components and their dependencies.
- **ERD** — a data model and its relationships.
- **State** — a lifecycle and its transitions.

If a board needs two of these, split it into two boards.

## Clarity and accessibility

- Consistent flow direction (top-to-bottom or left-to-right); label every edge.
- High contrast; never encode meaning in color alone (color-blind-safe).
- Generous spacing; group related nodes; keep node labels short.
- Always describe the diagram in prose too.

## Fallback order

1. **Figma FigJam** — always, when the Figma MCP is reachable.
2. **Prose description** — when Figma is unavailable (no plugin, headless, cron, or an interactively-authed server that's absent in this run), describe the diagram precisely in text *as part of the content itself*, written for the reader. Do not put tool-availability narration ("Figma MCP is not reachable in this run…") or a "board to be created later" note inside the deliverable — that follow-up belongs in the delivery message around the artifact. If the content needs no diagram, say nothing about diagrams at all; never emit a diagram section as boilerplate.
3. **Mermaid / Excalidraw** — last resort only, and flagged as temporary, to be replaced by a FigJam board.

Never default to Mermaid because it is quick. Quick is not the goal; a durable, editable asset is.
