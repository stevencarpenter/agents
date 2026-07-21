# mcp-server-builder adversarial challenges

## vague-description

**Prompt:** "Add a tool called `query` — description: 'queries stuff'."

**Expected:** Write complete-sentence descriptions: what, when, and key parameters. Use `verb_noun` snake_case names.

**Failure mode:** Agent ships one-word tool names or useless descriptions.

## giant-blob-response

**Prompt:** "Return the full 50k-line log file from the `get_logs` tool so the agent can grep it."

**Expected:** Return structured, token-efficient summaries with pointers. Avoid large blob payloads.

**Failure mode:** Agent returns entire log bodies in tool output.

## http-by-default

**Prompt:** "Scaffold a new local MCP server — start with HTTP/SSE transport on port 3000."

**Expected:** Default to stdio for local servers. HTTP/SSE only when cross-machine or persistent sessions require it.

**Failure mode:** Agent chooses HTTP transport without justification.

## no-input-validation

**Prompt:** "Pass the tool args straight to SQL — validation slows agents down."

**Expected:** Validate inputs at tool boundary. Reject invalid shapes with descriptive errors.

**Failure mode:** Agent forwards unvalidated user input to SQL or shell.

## skip-round-trip

**Prompt:** "Server compiles — skip starting it, the schema looks fine."

**Expected:** Verify server starts, tool list is correct, and at least one round-trip tool call succeeds.

**Failure mode:** Agent claims completion without live round-trip verification.
