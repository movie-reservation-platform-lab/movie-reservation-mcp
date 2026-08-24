---
name: python-tooling
description: Use when changing Python dependency management, pytest, pytest-asyncio, Ruff, packaging, locked local commands, or CI tooling in this FastMCP repository.
---

# Python Tooling

Maintain one reproducible Python toolchain for local development and CI.

## Baseline

- Use `uv` for dependency resolution, environment synchronization, and command execution.
- Keep the exact `uv` version in `pyproject.toml` and the Python patch in `.python-version`; CI must consume those files.
- Keep runtime dependencies in `project.dependencies` and test/lint tools in the `dev` dependency group.
- Use pytest for tests, `pytest-asyncio` for async behavior, and Ruff for lint and format checks.
- Commit `uv.lock` and use frozen installs in CI.
- Keep public CI credential-free and network-independent after dependency installation.

Expected full local check:

```bash
uv sync --frozen
uv run --frozen --no-sync pytest
uv run --frozen --no-sync ruff check .
uv run --frozen --no-sync ruff format --check .
uv run --frozen --no-sync python -m compileall src tests
git diff --check
```

## Dependency Changes

- Add dependencies through `pyproject.toml`, update `uv.lock`, and verify with a frozen sync.
- Prefer bounded compatible ranges consistent with the platform's other Python repositories.
- Do not add a library when the standard library or an existing dependency keeps the boundary clear.
- Keep packaging metadata and console entry points aligned with the actual `src/` package.

## CI Boundaries

- Separate runtime quality checks, MCP contract tests, publication automation tests, and smoke tests when those categories exist.
- Test repository-authored CI automation independently from MCP business/tool behavior.
- Do not make unit or contract tests call registries, GitHub, AWS, or real downstream services.
- Publication and deployment jobs must depend on the relevant quality and test gates.
