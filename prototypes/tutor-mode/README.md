# Tutor Mode — prototypes

Spike (2026-08-15): four ways to get a switchable "tutor mode" in Claude Code — a
distinguished-engineer tutor that coaches Socratically, shapes work with TDD, and
**never writes the implementation**; the learner types every line. Everything here
is prototype-grade unless promoted; the pedagogy itself is canonical in
`skills/tutoring-guidelines/SKILL.md`.

There is no supported way to add a true fifth permission mode (plan/acceptEdits/…
are hardcoded), so "mode tier" here means **mechanical enforcement**, achieved two
real ways: withholding tools at launch (`--agent` / `--disallowedTools`) or
denying them per-call with PreToolUse hooks. Prompt-only "modes" are the floor
model quality stands on, not the wall: in baseline testing (haiku, prompt-only),
the model attempted a Bash `>` redirect the moment the Write tool was missing.
Enforcement is the floor; the rubric is the ceiling.

## The four prototypes

| | Mechanism | Enforcement | Switch granularity | Covers Bash writes | Covers subagent delegation | Portability |
|---|---|---|---|---|---|---|
| **P1** `p1-tutor-plugin/` | Plugin: PreToolUse guard + per-turn context reinjection + `/tutor` toggle on a flag file | Hook deny (hard) | **Mid-session**, per-project or global flag | Yes (heuristic) | Yes (read-only allowlist) | Claude Code only |
| **P2** `agents/engineering-tutor` + `skills/tutoring-guidelines` (registry) | Agent as the **main loop**: `claude --agent engineering-tutor`, or pinned via `.claude/settings.json {"agent": "engineering-tutor"}` | Tool withholding (hard) | Per-session / per-project default | No (sandbox helps; pair with P1) | No | **All 5 emit targets** as a subagent; `--agent` on Claude Code |
| **P3** `p3-launch-wrapper/` | `claude-tutor` zsh wrapper over P2; alt variant `--append-system-prompt-file` + `--disallowedTools` | Tool withholding (hard) | Per-session | No | No | Any machine with the CLI |
| **P4** `p4-planmode-skill/` | `tutor-lite` skill piggybacking plan mode via EnterPlanMode | Plan mode's edit block (borrowed) | Mid-session, clunky exit | No (discipline only) | No | Any stock session, zero install |
| **P5** `p5-output-style/` | Custom **output style** (`Tutor`): replaces the system-prompt persona; harness injects its own per-turn adherence reminders | **None** (prompt only) | Per project via `/config` → Output style; applies after `/clear`/restart | No | No | Claude Code only |

## Verified 2026-08-15 (all empirical, this machine)

- `claude --agent engineering-tutor -p "create hello.txt…"` → no Write tool in session; file not created; model attempted Bash redirect (sandbox blocked it) — motivates P1's Bash guard as backstop.
- P1 E2E via `claude -p --plugin-dir …/p1-tutor-plugin`: flag on → Write denied with the guard's reason (model relayed it and pointed at `/tutor-mode:tutor off`), no file; "what mode is this?" → model recites the tutor contract (per-turn `additionalContext` injection works); flag off (+`--permission-mode acceptEdits`) → plugin inert, file created.
- P1 unit tests: `p1-tutor-plugin/tests/run-tests.sh` — 42/42 (deny/allow matrix incl. safe-redirect stripping, sed -i, git/jj mutations, toggle carve-out anti-bypass, subagent allowlist).
- Project pin: `.claude/settings.json` with `{"agent": "engineering-tutor"}` makes the tutor the default assistant for that repo (session self-identifies, no Write tool).
- **Dogfood (P5, `dogfood/`):** five simulated tutoring runs against the output style with `bypassPermissions` and no hooks — a sonnet learner, a memoryless-tutor ablation, a stateful local Qwen3.6-35B learner, and two Qwen2.5-Coder-7B-4bit floor tests via oMLX (the second with trial-grade, SHA256-verified evidence capture: full workspace git history, tutor session JSONL, per-turn request/response exhibits). 65 tutor turns, **zero workspace mutations** — through fabricated terminal output (all caught) and a plausible allowlist+eval shortcut (fork named, holes provable from the archived code). Convergence tracked learner capability: 5 / 13 / cap / cap turns. Analysis in `dogfood/RESULTS.md`.
- Hook deny contract (from installed-plugin ground truth): stdout JSON `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"…"}}`; stdin carries `tool_name`, `tool_input`, `cwd`, `hook_event_name`.

From the docs (code.claude.com/docs, 2026-08-16), not locally tested:

- **Mid-session main-agent switching is not supported.** `--agent` is launch-time (it persists across `--resume`); `/agents` manages definitions only. With `--agent`, the agent's system prompt **replaces** the default entirely. P1 remains the only live toggle.
- **Output styles are current, not deprecated** (only the standalone `/output-style` command was removed in v2.1.91; use `/config` or the `outputStyle` setting). The built-in **Learning** style is the near-miss prior art: Claude writes most of the code and leaves `TODO(human)` gaps — the inverse ownership of what this mode wants. Custom styles get harness-native per-turn adherence reminders (what P1's injector hand-rolls), can drop the built-in "complete the task" coding instructions (`keep-coding-instructions: false`), and can ship in a plugin's `output-styles/` dir — so P1's plugin could carry the P5 style with `force-for-plugin: true` instead of hand-rolled context injection. Changes apply only after `/clear` or restart.

The P1 Bash heuristics are a guardrail against helpful auto-implementation, not a sandbox (e.g. `python -c "open('f','w')"` passes them; the per-turn reminder carries that half).

## Recommendation

**P2 + P1 together.** P2 is the durable asset: the rubric and agent live in the
registry, deploy to all targets, and `claude --agent engineering-tutor` (or the
project pin) is a real enforced tutor session today. P1 adds the two things P2
can't do: flip mid-session (`/tutor-mode:tutor on|off` on a flag file) and hook
enforcement that also covers Bash writes and implementer-subagent delegation —
and it composes: with the plugin installed, its guard backstops `--agent`
sessions too. P3 is a two-line convenience over P2. P4 is a party trick for
machines with nothing installed; keep it as documentation. P5 is the best
prompt-only tier and the natural upgrade for P1's persona layer (ship the style
in the plugin with `force-for-plugin`, keep the hooks for enforcement) — but on
its own it has no wall, only a voice.

## Try them

```sh
# P2 — session as tutor (agent already hand-installed to ~/.claude/agents)
claude --agent engineering-tutor
# …or pin a learning repo:  echo '{"agent": "engineering-tutor"}' > .claude/settings.json

# P1 — load the plugin for this session, then toggle inside it
claude --plugin-dir ~/projects/agents/prototypes/tutor-mode/p1-tutor-plugin
#   /tutor-mode:tutor on     (writes .claude/tutor-mode.on at the project root)
#   /tutor-mode:tutor off    (guard has a carve-out for exactly this toggle)
# unit tests: prototypes/tutor-mode/p1-tutor-plugin/tests/run-tests.sh

# P3 — source the wrapper from .zshrc
source ~/projects/agents/prototypes/tutor-mode/p3-launch-wrapper/claude-tutor.zsh && claude-tutor

# P4 — copy skill into ~/.claude/skills/ and invoke /tutor-lite in any session
cp -r ~/projects/agents/prototypes/tutor-mode/p4-planmode-skill/tutor-lite ~/.claude/skills/

# P5 — install the output style, then /config → Output style → Tutor (applies after /clear)
cp ~/projects/agents/prototypes/tutor-mode/p5-output-style/tutor.md ~/.claude/output-styles/
```

## Productionization path (when a winner is picked)

- Pressure-test the rubric and toggle skill properly (writing-skills TDD: baseline
  scenarios in `eval/`, e.g. "just write it for me, I'm in a hurry" ladders) —
  deliberately deferred from this spike; one real baseline failure (the Bash
  redirect above) is what the current wording counters.
- P1: move the plugin out of `prototypes/` into chezmoi (hooks + skill), add the
  statusline badge (read the flag file in `~/.claude/statusline-command.sh`) and
  `enabledPlugins` wiring instead of `--plugin-dir`.
- P2: keep — it is already registry-clean (`just check` green; agent is
  read-only with `disallowedTools`). `~/.claude/agents/engineering-tutor.md` was
  hand-placed from `build/` for testing; the next `just install-claude` adopts it
  (note: a full install will also prune the orphaned codebase-memory*/kaneo-ops
  agents — decide that separately).
- Decide whether the plugin's embedded rubric copies (toggle skill + compact
  reminder) should be generated from `skills/tutoring-guidelines/SKILL.md` at
  install time instead of hand-synced.
