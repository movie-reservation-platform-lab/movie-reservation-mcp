# Implementation Plan: Reservation MCP container security gate

## 1. Summary

Update existing PR #9 for issue #7 using the reviewed recommendation-MCP #11
pattern, with reservation-specific image scans and MCP validation. Planning is
followed by implementation under the user's request to complete and validate it.

## 2. Goals

- Pin both publication actions and PR tooling to
  `bb40579c285df0b581c48b10f9b34574d5c78639` (merged actions PR #13).
- Adopt v1alpha3 evidence and a read-only PR production-image vulnerability gate.
- Remediate this image's blocking findings, retain complete diagnostics and
  verify the installed MCP runtime, then update existing PR #9 with `[ai]` prefix.

## 3. Non-goals

No exemptions, publication dispatch, merge, admission, deployment, AWS changes,
or edits to sibling repositories. Preserve local guidance changes on `main`.

## 4. Current State

PR #9 branch `issue7-container-candidate-evidence` is already checked out cleanly
at `9371ab3` in `.worktrees/movie-reservation-mcp-evidence`. The main worktree has
uncommitted AGENTS.md/hybrid-teaching guidance; work remains isolated from it.
`.github/workflows/ci.yml` has four validation jobs and main-only publication,
using old shared SHA `9b7b5a6` and default v1alpha2. `Dockerfile` includes uv,
curl and source in production on Bookworm. `automation/tests/test_release_contract.py`
has four workflow/image contract tests. Application dependencies are locked by uv.
Recommendation-MCP #11 is merged and provides the reviewed workflow and runtime
stage pattern; its scan counts are not evidence for this image.

## 5. Requirements and Assumptions

### Confirmed Requirements

Keep tool names, configuration, port 8091, health route, UID 10001, existing check
names and publication boundaries. Scan all severities and unfixed OS/library
findings through the shared evaluator. Do not suppress findings or add exemptions.

### Assumptions

The reviewed sibling pattern is appropriate for this Python service. Refresh
Python lock dependencies only if this image's findings require it. Existing PR
update includes pushing this branch, but does not authorize merging it.

### Open Questions

Which vulnerabilities affect the actual reservation image? Does runtime slimming
and a maintained base with fixed OS packages resolve its blockers? Determine by
building/scanning, then record actual results below. Environment issue #82 is
still open; v3 admission readiness is separately owned.

## 6. Proposed Design

Use the shared local scan helper in a separate `contents: read` job for
non-canonical runs, matching recommendation-MCP #11. Check out tooling at the
reviewed SHA, disable persisted credentials, install Node 24, build linux/amd64
`prod`, and provide GH_TOKEN only to v3 evaluation for component reservation-mcp.
Upload the full diagnostic directory after failure with 14-day retention and
missing files treated as an error. Canonical publication independently scans its
published digest using explicit `evidence-version: v1alpha3`.

Use separate build/development stages and a minimal Trixie production runtime.
Production copies only the non-editable virtual environment; Python urllib
replaces curl for health checks. Install current fixed OS packages based on scans.
An optional development stage retains uv, curl, source and offline tests.

## 7. Alternatives Considered

- Only update shared action pins: small but leaves PRs unable to detect image
  failures and does not explicitly select v3. Rejected.
- Duplicate scanner/evaluator or add local ignores: drifts from publication and
  weakens the shared policy contract. Rejected.
- Adopt the reviewed shared helper and slim runtime: chosen; adds scan latency
  and a base migration, verified by independent image and MCP checks.

## 8. API / Interface Changes

Application APIs unchanged. Candidate artifact becomes
`component-candidate-evidence-v1alpha3.json` with its policy evaluation companion.
PR diagnostics use `reservation-mcp-pr-vulnerability-report-RUN-attempt-ATTEMPT`;
these local-image reports provide no signed publication/admission authority.

## 9. Data Model / Persistence Changes

None. Diagnostics remain ignored locally and are retained in CI for 14 days.

## 10. Security, Privacy, and Abuse Considerations

No PR package-write, OIDC or attestation authority. Tokens only reach the evaluator;
no arbitrary policy override, ignored findings or failed-command suppression.
Keep exact action pins and main/repository publication guards. Exclude shared
tooling, reports, local environment files and caches from the build context.

## 11. Performance, Scalability, and Reliability Considerations

Scan job has a 20-minute budget; shared helper bounds scanning and policy fetch.
PR cancellation remains enabled; canonical publication remains non-cancelling.
Complete output survives a blocking policy result or operational failure where
produced. No runtime request-path changes.

## 12. Implementation Steps

1. Build and scan the existing production target as a reservation baseline.
2. Update `.github/workflows/ci.yml` with reviewed pins, v3 input and PR job;
   extend `automation/tests/test_release_contract.py` for authority/retention.
3. Update `Dockerfile`, `.dockerignore`, `.gitignore` for isolated stages and
   fixed OS packages; adapt only package changes justified by findings.
4. Update README reproduction/evidence docs and this plan's validation record.
5. Run frozen checks; build/scan production; verify health, real MCP negotiation,
   tool listing/call, UID and image contents; build/test development offline.
6. Request read-only security and maintainability review with file/line findings,
   resolve defects, push the existing branch, refresh PR #9 title/body and verify
   hosted CI plus its complete downloaded vulnerability diagnostics.

## 13. Testing Strategy

Run `uv sync --frozen`, `uv run --frozen --no-sync pytest tests automation/tests`,
Ruff check/format, compileall src/tests/automation, and git diff --check. Contract
tests protect workflow authority and failure retention. Docker live checks remain
separate from offline tests; a local downstream stub serves the real health/MCP
check. Run the shared v3 helper against this image with no exemption changes.

## 14. Rollout / Migration Plan

Update PR #9 only; no merge/dispatch. After a separately authorized merge, a fresh
canonical main run must produce v3 evidence. Environment v3 reader/admission
activation remains a separate gate under issue #82. Rollback reverts this PR's
workflow/runtime changes; older v2 runs do not substitute for v3 acceptance.

## 15. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
| --- | --- | --- | --- |
| Different OS/Python findings from sibling | Gate failure | Medium | Scan this image before and after remediation |
| Runtime stage loses dependencies | MCP startup failure | Medium | Real health and MCP call in built image |
| Policy/database unavailable | Gate fails closed | Medium | Retain diagnostics; fix cause and retry |
| Moving base and database | Results change later | High | Record image ID, report hash, policy revision/time |
| Worktree changes overwritten | Lost local work | Low | Use existing clean PR worktree |

## 16. Done Criteria

PR #9 updated with current dependencies and `[ai]` prefix; reviewed shared pins,
v3 gate, offline checks, real image/MCP checks and hosted scan pass. Complete
findings retained and blocking findings remediated without exemptions. No
publication or environment mutations performed.

## 17. Review Checklist

- [x] Requirements, non-goals and ownership explicit
- [x] Existing and sibling implementations inspected
- [x] Alternatives, security and reliability considered
- [x] Testing, ordered steps, rollout and rollback defined
- [x] Independent reviews completed; no material findings
- [ ] Local and hosted validation recorded

## 18. Handoff Prompt for Implementation Agent

Implement this plan on the existing PR #9 worktree, preserving main's local
changes. Reuse the reviewed shared security helper; fix actual findings without
exemptions, verify installed MCP functionality and offline checks, and update
existing PR #9. Do not publish, merge, dispatch, admit or deploy.

## Validation Record

### Local validation (2026-09-14)

- Existing Bookworm production image: policy failed with 5 CRITICAL / 68 HIGH
  at `2026-09-14T20:56:20Z`. Complete baseline diagnostics retained locally in
  `.local-container-security/baseline/` (ignored).
- Blocking packages: libsqlite3-0 `3.40.1-2+deb12u2` (CVE-2025-7458), perl-base
  `5.36.0-7+deb12u3` (CVE-2026-13221, CVE-2026-42496, CVE-2026-8376), and
  zlib1g `1:1.2.13.dfsg-1` (CVE-2023-45853). No exemptions were requested.
- The Trixie runtime installs perl-base `5.40.1-6+deb13u1`, libsqlite3-0
  `3.46.1-7+deb13u1`, and zlib1g `1:1.3.dfsg+really1.3.1-1+b1`. Python lock
  dependencies did not require changes to clear blocking findings.
- Rebuilt production image: **passed, 0 CRITICAL / 49 HIGH, zero exemptions**,
  evaluated at `2026-09-14T20:58:22Z` against central revision
  `bb40579c285df0b581c48b10f9b34574d5c78639`, using shared Trivy 0.70.0.
  Complete remediated diagnostics retained in `.local-container-security/remediated/`.
- Local image ID:
  `sha256:4ea580856f0fde895a6217e43f866fe1577c067398691d6b26aae41ac771b2ce`.
  Complete report SHA-256:
  `bffde27b4ed6aefe6fe295f54a7ad3cf8bef0e90db40e7392f253a9438993557`.
  Baseline report SHA-256:
  `573d4ed63ba8ea1c00871475624c33427c8a8ad787abda31b40ea76428d8a445`.
- Frozen pytest: 23 passed (15 runtime, 8 automation). Ruff lint/format,
  compileall and diff checks passed. Development image built and all 23 tests
  passed with container networking disabled.
- Production health, real FastMCP negotiation, exact four-tool listing and
  `reservation_health` invocation passed against a local downstream stub.
  UID 10001, absent uv/uvx/curl/source, and the Docker HEALTHCHECK passed.
  GraphQL operations retain offline tool/adapter coverage; live smoke uses health.
- Independent read-only security and maintainability reviews found no material
  defects. The preset reviewers' model was unavailable, so reviews used available
  agents with the same repository review instructions.
- Hosted CI and downloaded artifact verification follow the branch push; the
  exact run and observed result will be recorded in PR #9 without dispatching
  publication or modifying environment state.

Primary package status supporting the selected base/package remediation:
[SQLite](https://security-tracker.debian.org/tracker/CVE-2025-7458),
[Perl](https://security-tracker.debian.org/tracker/CVE-2026-13221), and
[zlib](https://security-tracker.debian.org/tracker/CVE-2023-45853).
The complete Trivy findings determine the gate; no local ignore overrides apply.
