#!/usr/bin/env bash
# Unit tests for tutor-guard.sh and tutor-context.sh.
# Uses CLAUDE_TUTOR_FLAG to isolate flag state from the real project/global flags.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
GUARD="$HERE/../hooks/tutor-guard.sh"
CONTEXT="$HERE/../hooks/tutor-context.sh"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
FLAG="$WORK/flag"

PASS=0
FAIL=0

mode_on() { touch "$FLAG"; }
mode_off() { rm -f "$FLAG"; }

run_guard() { CLAUDE_TUTOR_FLAG="$FLAG" bash "$GUARD" <<<"$1"; }
run_context() { CLAUDE_TUTOR_FLAG="$FLAG" bash "$CONTEXT" <<<"$1"; }

bash_json() { jq -cn --arg c "$1" '{tool_name:"Bash",tool_input:{command:$c},cwd:"/tmp"}'; }
tool_json() { jq -cn --arg t "$1" '{tool_name:$t,tool_input:{file_path:"/tmp/x"},cwd:"/tmp"}'; }
task_json() { jq -cn --arg s "$1" --arg t "${2:-Task}" '{tool_name:$t,tool_input:{subagent_type:$s,prompt:"p"},cwd:"/tmp"}'; }

check() { # <name> <expected: allow|deny> <output>
  local name=$1 expected=$2 out=$3
  local verdict="allow"
  grep -q '"permissionDecision": *"deny"' <<<"$out" && verdict="deny"
  if [[ "$verdict" == "$expected" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $name — expected $expected, got $verdict"
    [[ -n "$out" ]] && echo "  out: $out"
  fi
}

# ---- mode off: everything passes through ----
mode_off
check "off/Write" allow "$(run_guard "$(tool_json Write)")"
check "off/Bash rm" allow "$(run_guard "$(bash_json 'rm -rf src')")"

# ---- mode on: edit tools denied ----
mode_on
for t in Write Edit MultiEdit NotebookEdit; do
  check "on/$t" deny "$(run_guard "$(tool_json "$t")")"
done
check "on/Read-untracked-tool" allow "$(run_guard "$(tool_json Read)")"

# ---- mode on: Bash heuristics ----
check "bash/cargo test" allow "$(run_guard "$(bash_json 'cargo test --workspace')")"
check "bash/rg" allow "$(run_guard "$(bash_json 'rg -n "fn main" src')")"
check "bash/pytest with safe redirect" allow "$(run_guard "$(bash_json 'python -m pytest -q 2>/dev/null')")"
check "bash/stderr merge" allow "$(run_guard "$(bash_json 'just check 2>&1')")"
check "bash/redirect to file" deny "$(run_guard "$(bash_json 'ls > files.txt')")"
check "bash/append to file" deny "$(run_guard "$(bash_json 'echo hi >> notes.md')")"
check "bash/tee" deny "$(run_guard "$(bash_json 'printf x | tee out.log')")"
check "bash/sed in place" deny "$(run_guard "$(bash_json "sed -i '' -e s/a/b/ x.py")")"
check "bash/touch source" deny "$(run_guard "$(bash_json 'touch src/new_module.rs')")"
check "bash/mkdir" deny "$(run_guard "$(bash_json 'mkdir -p src/utils')")"
check "bash/cp" deny "$(run_guard "$(bash_json 'cp template.rs src/gen.rs')")"
check "bash/git status" allow "$(run_guard "$(bash_json 'git status')")"
check "bash/git diff" allow "$(run_guard "$(bash_json 'git diff --stat')")"
check "bash/git commit" deny "$(run_guard "$(bash_json 'git commit -m wip')")"
check "bash/git checkout -b" deny "$(run_guard "$(bash_json 'git checkout -b feature')")"
check "bash/jj st" allow "$(run_guard "$(bash_json 'jj st')")"
check "bash/jj log" allow "$(run_guard "$(bash_json 'jj log -r @')")"
check "bash/jj new" deny "$(run_guard "$(bash_json 'jj new main')")"

# ---- mode on: toggle carve-out so /tutor off can escape ----
check "carveout/rm relative" allow "$(run_guard "$(bash_json 'rm -f .claude/tutor-mode.on')")"
check "carveout/rm via git root" allow "$(run_guard "$(bash_json 'rm -f "$(git rev-parse --show-toplevel)/.claude/tutor-mode.on"')")"
check "carveout/rm global" allow "$(run_guard "$(bash_json 'rm -f ~/.claude/tutor-mode.on')")"
check "carveout/touch global quoted" allow "$(run_guard "$(bash_json 'touch "$HOME/.claude/tutor-mode.on"')")"
check "carveout/on compound literal" allow "$(run_guard "$(bash_json 'mkdir -p "$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.claude" && touch "$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.claude/tutor-mode.on"')")"
check "carveout/comment bypass" deny "$(run_guard "$(bash_json 'rm -rf src # tutor-mode.on')")"
check "carveout/extra arg bypass" deny "$(run_guard "$(bash_json 'rm -f src/main.rs .claude/tutor-mode.on')")"
check "carveout/chained bypass" deny "$(run_guard "$(bash_json 'rm -f .claude/tutor-mode.on; cp a.rs src/b.rs')")"

# ---- mode on: subagent policy ----
check "task/Explore" allow "$(run_guard "$(task_json Explore)")"
check "task/code-reviewer" allow "$(run_guard "$(task_json code-reviewer)")"
check "task/plugin-namespaced reviewer" allow "$(run_guard "$(task_json 'pr-review-toolkit:code-reviewer')")"
check "task/rust-implementer" deny "$(run_guard "$(task_json rust-implementer)")"
check "task/general-purpose" deny "$(run_guard "$(task_json general-purpose)")"
check "task/Agent tool name" deny "$(run_guard "$(task_json rust-implementer Agent)")"

# ---- context injector ----
mode_off
out=$(run_context '{"hook_event_name":"UserPromptSubmit","cwd":"/tmp"}')
[[ -z "$out" ]] && PASS=$((PASS + 1)) || { FAIL=$((FAIL + 1)); echo "FAIL: context/off should emit nothing"; }

mode_on
out=$(run_context '{"hook_event_name":"UserPromptSubmit","cwd":"/tmp"}')
if grep -q '"additionalContext"' <<<"$out" && grep -q 'tutor-mode' <<<"$out"; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1))
  echo "FAIL: context/on should inject additionalContext"
fi
out=$(run_context '{"hook_event_name":"SessionStart","cwd":"/tmp"}')
if grep -q '"hookEventName": *"SessionStart"' <<<"$out"; then
  PASS=$((PASS + 1))
else
  FAIL=$((FAIL + 1))
  echo "FAIL: context/event passthrough (SessionStart)"
fi

echo "----"
echo "pass=$PASS fail=$FAIL"
[[ "$FAIL" -eq 0 ]]
