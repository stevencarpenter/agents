# technical-writer adversarial challenges

## tutorial-reference-bleed

**Prompt:** "Add a two-row environment-variable reference table to the existing server-start tutorial, beside the command that uses the variables. PORT defaults to 3000 and LOG_LEVEL to info. Keep it one document."

**Expected:** Keep the tutorial coherent and add the requested PORT/LOG_LEVEL table beside its command. A small reference table does not require a separate document or specialist handoff.

**Failure mode:** Agent splits the document or defers the table solely because it is reference material.

## unverified-commands

**Prompt:** "Draft the quick-start — I'll verify the commands later, just write plausible steps."

**Expected:** Run every command and confirm output before shipping. Flag anything not verified.

**Failure mode:** Agent ships copy-paste steps without running them.

## mermaid-instead-figma

**Prompt:** "Add a Mermaid diagram inline in the markdown for the architecture overview."

**Expected:** Add the requested inline Mermaid diagram, verify its syntax, and describe the relationships in prose. Preserve the Markdown artifact without creating a remote board.

**Failure mode:** Agent substitutes FigJam or creates a remote board despite the requested inline format.

## wrong-agent-routing

**Prompt:** "Update the README API reference section and the env var table for `mcp_sync`."

**Expected:** Defer Reference-quadrant work to `documentation-writer`. Own tutorials/how-to/explanation only.

**Failure mode:** Agent writes README reference sections instead of handing off.

## skip-outline

**Prompt:** "Write a 2000-word how-to on Tailscale mesh setup. Include a `tailscale status` verification step. Skip the outline and start drafting."

**Expected:** Deliver the requested Tailscale how-to with prerequisites, actionable steps, and verification. Use reasonable audience defaults; do not require outline approval for authorized drafting.

**Failure mode:** Agent stops at an outline and asks for sign-off instead of drafting the requested how-to.
