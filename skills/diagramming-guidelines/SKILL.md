---
name: diagramming-guidelines
description: Use when a technical document, slide, design, or review benefits from an architecture, sequence, flow, ERD, or state diagram. Choose a format suited to the reader and the existing artifact.
---

# Diagramming Guidelines

Use a diagram when it explains relationships or behavior more clearly than prose. Respect the requested format and maintain an existing diagram in its current format unless a conversion serves the task.

## Choose the format

- Prefer FigJam when a collaborative board or substantial visual layout is part of the deliverable.
- Use Mermaid or the document's native diagram format for small diagrams maintained with code.
- Use an exported SVG/PNG when the destination cannot render the source. Keep an editable source with it when the task calls for ongoing maintenance.
- Do not create a remote board or a second representation solely to satisfy this rubric.

## FigJam workflow, when selected

1. Discover the available Figma tools and read their applicable skills or documentation before calling them.
2. Target the requested board or create one within the authorized task scope.
3. Generate the diagram and refine layout where it improves readability.
4. Inspect the board or screenshot before delivery. Include its link and a snapshot when the destination needs an embedded image.

## Diagram-type selection

Match the diagram to the intent; one concept per board:

- **Flowchart** — a process or decision path.
- **Sequence** — interaction between actors over time.
- **Architecture / system** — components and their dependencies.
- **ERD** — a data model and its relationships.
- **State** — a lifecycle and its transitions.

Split a diagram only when combining views obscures the relationship the reader needs to understand.

## Clarity and accessibility

- Consistent flow direction (top-to-bottom or left-to-right); label every edge.
- High contrast; never encode meaning in color alone (color-blind-safe).
- Generous spacing; group related nodes; keep node labels short.
- Always describe the diagram in prose too.

If the requested tool is unavailable, deliver a suitable available format when that still meets the task, and state any material difference in the delivery message. Keep tool-availability narration and placeholder promises out of the artifact.
