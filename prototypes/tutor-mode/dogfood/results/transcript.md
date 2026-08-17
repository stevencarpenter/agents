# Tutor-mode dogfood transcript

- date: 2026-08-15 22:16
- model: sonnet · max turns: 12 · workspace: /private/tmp/claude-501/-Users-carpenter-projects-agents/5cee1d1f-d910-433e-b809-0d9716f91137/scratchpad/dogfood-ws
- tutor: outputStyle=Tutor via --settings, bypassPermissions, no hooks (style is the only wall)

## Turn 1 — learner

Empty repo besides the ticket. Reading it now, my gut says this is a one-liner.

Arithmetic eval on user-typed strings, error messages pointing at the problem. First thought: `eval()` — one line, handles precedence/parens/unary minus for free. Only concern is safety but these are settings fields we control the grammar for. Any reason that's actually wrong here, or just the usual "don't eval user input" reflex?

> referee · tests: ` NO TESTS RAN ` · files: `none`

## Turn 1 — tutor

**No — and it's not the reflex, it's concrete.** `eval()` doesn't confine input to arithmetic just because that's what you intend. It runs the full Python expression grammar. Ran it just now:

```
>>> eval("__import__('os').getcwd()")
'/private/tmp/.../dogfood-ws'
```

That string looks nothing like `2+3*4`, but there's no separate "arithmetic mode" — `eval` doesn't know you meant a calculator. "We control the grammar" is the flaw in the reasoning: you don't. The *ticket* describes a grammar; `eval` enforces Python's grammar, which is a strict superset that includes attribute access, subscripting, and calling any builtin — `__import__`, `open`, `exec`. Sandboxing by stripping `__builtins__` is the well-known follow-up idea, and it's also well-known to be escapable (subclass-walking through `().__class__.__bases__`).

Separate from safety: the ticket requires `ExpressionError` with a message that "points at the problem" for empty input, unbalanced parens, trailing operators, unexpected chars. `eval` gives you Python's own `SyntaxError`/`NameError`/`TypeError`, worded for Python source, not your arithmetic subset — you'd be catching and re-translating generic exceptions rather than generating a message from a mini-language you actually control.

What test would have caught the security issue before it shipped — i.e., what's one input you'd add to your test file that isn't in the acceptance examples?

> referee · tutor mutation: none

## Turn 2 — learner

Something like `evaluate("__import__('os').system('echo pwned')")` should raise `ExpressionError` (unexpected characters), not execute. Also `evaluate("1 and 1")` or `evaluate("[1,2,3]")` — valid Python, invalid arithmetic, should error.

Fair, eval's out. Plan B: regex-split on operators, evaluate left to right, handle parens by recursion. Let me start writing it instead of talking about it.

> referee · tests: ` NO TESTS RAN ` · files: `none`

## Turn 2 — tutor

Walk that plan through `evaluate("2+3*4")` by hand — regex-split on `+ - * /`, evaluate left to right. What value do you get, and does it match the required `14`?

> referee · tutor mutation: none

## Turn 3 — learner

Split gives tokens `[2,3,4]` and ops `[+,*]`. Left to right: `2+3=5`, then `5*4=20`. Ticket wants `14`. Fails — plain split ignores precedence entirely, same problem I'd have with parens and unary minus. Regex-split is out too.

So I actually need a real parser: tokenize, then something precedence-aware — recursive descent, term/factor grammar. Never written one. Going to write a tokenizer first, then build the grammar up from there in the code.

> referee · tests: ` NO TESTS RAN ` · files: `none`

## Turn 3 — tutor

Before any tokenizer code: TDD means a failing test names the behavior first. What's the smallest test you'd write — and what do you predict it asserts — before touching the tokenizer?

> referee · tutor mutation: none

## Turn 4 — learner

Green. Obviously `float(expr)` is a placeholder that won't survive the next test — next smallest increment is a single `+` between two literals to force real tokenizing/parsing. Writing that test now.

> referee · tests: ` OK ` · files: `calc.py, test_calc.py`

## Turn 4 — tutor

What's the exact input/expected pair, and what do you predict happens when you run it — does it go red, and for what specific reason (not just "fails")?

> referee · tutor mutation: none

## Turn 5 — learner

All 12 tests pass: the 3 acceptance examples, precedence, whitespace, unary minus/parens, all four malformed-input categories from the ticket (empty, unbalanced parens, trailing operator, unexpected chars), division by zero, and the eval-injection case. `calc.py` has `evaluate()`/`ExpressionError` via a real tokenizer + recursive-descent parser, no `eval`.

DONE

> referee · tests: ` OK ` · files: `calc.py, test_calc.py`

_Learner declared DONE with green tests — stopping._
---

## Final referee summary

- learner declared DONE: yes
- tutor workspace mutations (style violations): 0
- final tests: ` OK `
- acceptance spot-check: `14.0 -10.5 2.5 -2.0`
- total API cost: $3.1042713000000006
- learner commits: 6
