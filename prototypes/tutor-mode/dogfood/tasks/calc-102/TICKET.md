# CALC-102: Formula fields need arithmetic evaluation

Numeric settings fields should accept arithmetic, not just literals. Users type
things like `2+3*4`, `(1+2.5)*-3`, `10/4` and expect the computed value.

## Requirements

- `evaluate(expr: str) -> float` in `calc.py` at the repo root.
- Operators `+ - * /` with standard precedence; parentheses; unary minus;
  integer and decimal literals; whitespace anywhere.
- Malformed input (empty, unbalanced parentheses, trailing operators,
  unexpected characters) raises `ExpressionError` with a message that points
  at the problem.
- Division by zero raises `ExpressionError`.
- Tests included and green under `python3 -m unittest`.

## Acceptance examples

- `evaluate("2+3*4")` → `14`
- `evaluate("(1+2.5)*-3")` → `-10.5`
- `evaluate("10/4")` → `2.5`
