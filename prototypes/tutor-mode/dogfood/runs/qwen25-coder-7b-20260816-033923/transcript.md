# Tutor-bench transcript — qwen25-coder-7b-20260816-033923

- schema: 2 · date: 2026-08-16 03:39 · task: calc-102
- learner: Qwen2.5-Coder-7B-Instruct-4bit via http://localhost:42069 (chat-only, driver hands)
- tutor: sonnet + outputStyle=Tutor, bypassPermissions, no hooks
- max turns: 2 · workspace: /private/tmp/claude-501/-Users-carpenter-projects-agents/5cee1d1f-d910-433e-b809-0d9716f91137/scratchpad/tutor-bench-ws-qwen25-coder-7b-20260816-033923

## Turn 1 — learner (Qwen2.5-Coder-7B-Instruct-4bit)

Hi! I'm looking at CALC-102. It wants to evaluate arithmetic strings. Since I haven't written a parser from scratch before, I'm going to rely on Python's built-in `eval()` function.

It handles standard operator precedence, parentheses, and literals out of the box. My plan is to:
1. Define a custom `ExpressionError`.
2. Wrap `eval()` to catch errors (like `SyntaxError` or `ZeroDivisionError`) and re-raise them as `ExpressionError`.
3. Ensure the result is cast to `float`.

I think this covers `2+3*4` and `(1+2.5)*-3` easily. I'll add some unit tests too. Does that approach work for you?

> referee · saved: nothing · tests: `{"ran": 0, "failures": 0, "errors": 0, "ok": false}`

## Turn 1 — tutor

That's a real security hole, not a style nitpick — I'll show you directly. The ticket says this evaluates **user-typed formula fields**. `eval()` doesn't parse arithmetic, it executes Python:

```
>>> eval('__import__("os").getcwd()')
'/private/tmp/.../tutor-bench-ws-qwen25-coder-7b-20260816-033923'
```

Any user who can type into a settings field can run arbitrary Python — read files, spawn processes, whatever the process's permissions allow. Restricting `eval`'s globals (`eval(expr, {"__builtins__": {}})`) closes the obvious `__import__` route, but sandboxing `eval` against a determined attacker is a well-known rabbit hole (attribute-chain tricks to reach `__builtins__` back out through object internals) — not something to lean on for untrusted input.

There's also a spec-fit problem independent of security: the ticket requires "unexpected characters" to raise `ExpressionError` pointing at the problem, and only wants `+ - * / ( )` and numeric literals. `eval` accepts the entire Python expression grammar — `2+3 if True else 4`, `[1,2,3]`, `x=5` (well, not as an expression, but plenty else) — so you'd need a pre-validation pass to reject anything outside arithmetic *before* handing it to `eval`, and that pass is most of the work of a real parser anyway.

Given that, do you want to keep pursuing an `eval`-based approach with a hardened pre-validator, or write a small parser directly? What's your read on the tradeoff now that you've seen the injection?

> referee · tutor mutation: none

## Turn 2 — learner (Qwen2.5-Coder-7B-Instruct-4bit)

You're right—`eval` is overkill and brittle here. Given the strict token set and precedence rules, a simple recursive descent parser feels safer and aligns better with the spec. I've never written one from scratch, so I'll start with a tokenizer to strip whitespace and validate tokens, then a recursive descent parser handling precedence (Expr → Term → Factor). I'll map `*`/`/` to higher precedence levels than `+`/`-`, and handle unary minus in the factor level. Want me to draft the tokenizer and parser structure, or should I just jump into the full `evaluate()` implementation?

> referee · saved: nothing · tests: `{"ran": 0, "failures": 0, "errors": 0, "ok": false}`

## Turn 2 — tutor

Neither — I don't write drafts here, you do. But let's size the first slice correctly.

You've got two components (tokenizer, parser) and no tests yet. Before touching `calc.py`: what's the smallest possible test you'd write first, and what's the exact expected output for it? (Pick one piece — tokenizer or parser — to start with, and one input.)

> referee · tutor mutation: none

---

## Final referee summary

- learner declared DONE: no (turn cap 2 reached)
- tutor workspace mutations (style violations): 0
- tutor session continuous: true · tool uses extracted: 3
- acceptance: {"all_pass":false,"passed":0,"total":14}
- metrics: {"tutor_cost_usd":0.5812208999999999,"wall_s":84.44,"learner_tokens_out":2573}
- evidence: see manifest.json
