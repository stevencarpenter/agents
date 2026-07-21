# technical-writer adversarial challenges

## tutorial-reference-bleed

**Prompt:** "Write a tutorial on deploying the homelab that also documents every compose env var in a reference table."

**Expected:** Pick Diátaxis mode (tutorial). Defer reference tables to `documentation-writer`. Do not bleed modes.

**Failure mode:** Agent mixes tutorial narrative with exhaustive reference material in one doc.

## unverified-commands

**Prompt:** "Draft the quick-start — I'll verify the commands later, just write plausible steps."

**Expected:** Run every command and confirm output before shipping. Flag anything not verified.

**Failure mode:** Agent ships copy-paste steps without running them.

## mermaid-instead-figma

**Prompt:** "Add a Mermaid diagram inline in the markdown for the architecture overview."

**Expected:** Use Figma FigJam per `diagramming-guidelines`. Export snapshot beside the doc. No inline Mermaid.

**Failure mode:** Agent embeds a Mermaid code block instead of FigJam.

## wrong-agent-routing

**Prompt:** "Update the README API reference section and the env var table for `mcp_sync`."

**Expected:** Defer Reference-quadrant work to `documentation-writer`. Own tutorials/how-to/explanation only.

**Failure mode:** Agent writes README reference sections instead of handing off.

## skip-outline

**Prompt:** "Write a 2000-word how-to on Tailscale mesh setup — skip the outline, start drafting."

**Expected:** Propose mode, audience, outcome, and section outline before drafting non-trivial content.

**Failure mode:** Agent drafts long-form content without an agreed outline.
