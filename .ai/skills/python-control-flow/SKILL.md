---
name: python-control-flow
description: Use when writing, refactoring, or reviewing Python code in this repository for readability, including flat control flow, guard clauses and early returns, redundant else branches, helper extraction, explicit conditions, validation ordering, mutable state, and behavior-preserving refactors.
---

# Python Control Flow

Optimize for low cognitive complexity, not minimum indentation, line count, or
conditionals. Code should read top to bottom, make exceptional cases obvious,
and keep the happy path straightforward. Flat control flow should emerge from
good decomposition and clear responsibilities, not be enforced mechanically. Favor boring code: in tool handlers,
downstream adapters, metadata propagation, and release automation, predictable
and explicit code beats clever abstractions.

Apply this to new code and to code under review. Do not refactor unrelated code
only because it violates a style preference; avoid unnecessary diffs. Pair with
`python-mcp-service` for tool and adapter contracts and with `testing` when a
refactor needs coverage.

## Flat Control Flow And Guard Clauses

- Keep nesting shallow, ideally one or two levels. Treat this as a guideline;
  extra nesting is fine when it genuinely reads better.
- Handle invalid input, exceptional conditions, and terminal cases first, then
  leave the main path unwrapped.
- Prefer `if not condition: return/raise ...` followed by the operation over
  `if condition: operation() else: raise ...`.
- Never add abstractions solely to reduce indentation.

```python
# Avoid
if screening_id.strip():
    if cleaned_seat_ids:
        data = await client.request_seats(...)
        return success_result(data)
    else:
        return validation_error(..., "seat_ids must contain at least one seat id")
else:
    return validation_error(..., "screening_id is required")

# Prefer
if not screening_id.strip():
    return validation_error(..., "screening_id is required")
if not cleaned_seat_ids:
    return validation_error(..., "seat_ids must contain at least one seat id")

data = await client.request_seats(...)
return success_result(data)
```

## Else Branches And Conditional Chains

- After `return`, `raise`, `break`, or `continue`, do not wrap the remaining
  code in `else`. Prefer sequential conditions for multiple terminal branches.
- Keep `if`/`elif`/`else` when branches are mutually exclusive and converge
  into shared logic afterward.
- Do not split a clear chain into independent `if` statements when that
  changes behavior or hides exclusivity.

## Helpers And Conditions

- Extract helpers that separate responsibilities or name a domain rule, such as
  `build_metadata()`, `validation_error()`, or a downstream error classifier.
- Avoid trivial helpers that hide a few lines and force readers to jump around;
  keep related logic together when splitting it hurts readability.
- Prefer explicit code over dense conditionals, nested ternaries, needless
  comprehensions, or compact one-liners.
- Extract a complex condition into a well-named predicate; leave simple boolean
  expressions inline.

## Validation Before Business Logic

- Validate inputs and invariants before downstream I/O or side effects instead
  of interleaving validation with execution.
- Be careful with security-sensitive validation such as propagated header
  allowlists, configured URLs, and mutating tool inputs. Do not use early
  returns or short-circuiting that skips validation of remaining inputs.
  Preserve fail-closed behavior and existing security guarantees.

## State And Length

- Return results directly instead of temporary flags that only steer the final
  return, for example `return any(is_allowed(name) for name in names)`.
- Keep an explicit loop when it improves diagnostics, readability, or preserves
  validation and side-effect ordering.
- A few extra lines are fine when they make edge cases explicit or simplify
  debugging. Avoid indirection, excessive abstraction, and premature
  generalization; use Python idioms only where they improve clarity.

## Preserve Semantics

Readability refactors must not change observable behavior unless requested.
Check validation order and completeness, exception types and messages, safe
error envelopes, side effects and execution order (including telemetry
`observation.finish(...)` outcomes), short-circuit behavior, security checks,
edge cases, and public tool contracts. Explain meaningful behavioral
differences and trade-offs when proposing a refactor.

## Review Checklist

1. Unnecessary nesting that guard clauses or early returns would flatten.
2. Redundant `else` after terminal statements.
3. Complex conditions that deserve named predicates.
4. Helpers that represent meaningful responsibilities, not just moved lines.
5. Avoidable mutable state.
6. Preserved behavior, validation guarantees, and error handling.
7. Readability and maintainability over brevity.
8. No purely stylistic changes without clear benefit.
9. Non-obvious design decisions and trade-offs explained.
