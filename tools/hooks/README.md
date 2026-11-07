# Hooks

Scripts here are Claude Code hooks that the dotfiles wire into `settings.json`. This repo is
the canonical source so the scripts stay next to the agents and skills they refer to.

| Script | Event | What it does |
|---|---|---|
| `re-workspace-context.sh` | SessionStart | Prints the provenance labels, precedence rule, and agent list when the working directory is an REA workspace (`findings/` and `evidence/`), a findings package (`SPEC/README.md` with the label table), or a consumer repo that vendors one (`docs/research/*/SHA256SUMS`). Prints nothing elsewhere. |

Wire it like `emit-routing-context.sh`: a `SessionStart` command hook contributed to the Claude
settings resource by a dfm module (see `dfm-module-agents.toml` in dotfiles). The script reads the
hook JSON on stdin for `cwd` and falls back to the process working directory. Set `RE_HOOK_CWD`
to test it against another directory.
