# Movie Reservation MCP — AI Guidance

## Purpose

This repository owns the MCP wrapper around the movie reservation GraphQL API.
It exposes reservation tools for the Python reservation agent and forwards
distributed tracing/request metadata to the downstream API.

## Repository Rules

- Keep MCP tool names stable unless coordinating a consumer migration with
  `movie-reservation-agent`.
- Preserve propagation of `traceparent`, `tracestate`, `X-Correlation-Id`,
  `X-Request-Id`, and `X-Demo-Fault`.
- Keep downstream GraphQL configuration environment-driven.
- Do not deploy AWS resources from this repo.
- Publish immutable application artifacts; deployment composition belongs to
  the platform environment/infra repos.
- This scaffold is not production-ready until the golden-path/demo reservation
  MCP behavior is ported and covered by smoke tests.

## Commands

- Compile check: `python -m compileall src`
- Future dependency sync should be documented here when the runtime stack is
  selected.
