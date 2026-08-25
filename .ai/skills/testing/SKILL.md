---
name: testing
description: Use when creating, organizing, refactoring, or reviewing pytest coverage for Python FastMCP tools, HTTP adapters, metadata propagation, safe errors, health routes, and smoke-test boundaries.
---

# Testing

Keep MCP tests behavior-focused, network-independent by default, and organized
around the boundary that can fail. Pair with `python-tooling` when changing
dependencies, locked commands, Ruff, or CI.

## Baseline

- Use pytest for all tests and `pytest-asyncio` for async tool/client behavior.
- Prefer plain test functions and pytest fixtures over test classes.
- Keep mutable fixtures function-scoped and close async clients explicitly.
- Prefer narrow fakes for stateful clients and `httpx.MockTransport` for HTTP.
- Use `monkeypatch` or mocks only for narrow boundary replacement and hard-to-trigger failures.
- Keep ordinary tests offline; put real service smoke tests in a separate suite or job.

## Test Layers

- Unit tests: metadata normalization, URL derivation, validation, result/error mapping, and response parsing.
- Tool contract tests: call decorated tool functions with a fake downstream client and assert stable agent-visible results.
- HTTP adapter tests: assert method, URL, allowlisted headers, payload, timeout/error classification, and malformed responses.
- Process/route tests: cover health and lifecycle when outer transport behavior is the contract.
- Smoke tests: exercise real local services separately and never depend on AWS in public CI.

## Required Failure Coverage

- Invalid or blank identifiers and empty collections.
- Connection and timeout failures.
- Non-success HTTP and GraphQL/API errors.
- Non-JSON, wrong-shape, and missing-field responses.
- Allowed propagation headers present and blank/disallowed values omitted.
- Stable safe error envelopes without raw exception or downstream-body leakage.

## Organization

- Keep tests under `tests/` and name files after the boundary under test.
- Keep helpers and fixtures local until reuse across modules is proven.
- Add `conftest.py` only when shared setup genuinely reduces duplication.
- Name tests after observable behavior, not implementation methods.
- Use `pytest.mark.parametrize` only when each row protects the same behavior.

## Workflow

Run focused pytest tests while iterating. Before finishing, run the frozen pytest,
Ruff lint, Ruff format check, and compile commands defined by `python-tooling` and
the repository guidance.
