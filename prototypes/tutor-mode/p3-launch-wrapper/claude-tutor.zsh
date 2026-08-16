# claude-tutor — launch Claude Code as a tutor session.
# Source from .zshrc:  source ~/projects/agents/prototypes/tutor-mode/p3-launch-wrapper/claude-tutor.zsh
#
# Enforcement is launch-scoped: the whole session is a tutor session. For a
# mid-session toggle, use the p1 plugin instead (they compose — the p1 Bash
# guard also backstops these sessions if the plugin is loaded).

# Preferred: the registry `engineering-tutor` agent as the MAIN-loop assistant.
# Tool withholding (disallowedTools in the agent definition) is the enforcement:
# verified 2026-08-15 — the session has no Write/Edit tools at all.
claude-tutor() {
  claude --agent engineering-tutor "$@"
}

# No-registry variant: same rubric injected via system prompt, tools blocked at
# the CLI. Works on machines without ~/.claude/agents installed.
claude-tutor-prompt() {
  claude \
    --append-system-prompt-file "$HOME/projects/agents/skills/tutoring-guidelines/SKILL.md" \
    --disallowedTools Write Edit MultiEdit NotebookEdit \
    "$@"
}
