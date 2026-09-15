# Implementation Plan: Authenticated Prepare Adoption

## 1. Summary

[Issue #11](https://github.com/movie-reservation-platform-lab/movie-reservation-mcp/issues/11)
adopts merged [actions PR #18](https://github.com/movie-reservation-platform-lab/movie-platform-actions/pull/18),
which fixes [actions issue #14](https://github.com/movie-reservation-platform-lab/movie-platform-actions/issues/14),
at reviewed SHA `036531133bcefd454b5afc0eb55f8ba0328901ea`.
Use the validated [recommendation-MCP canary PR #13](https://github.com/movie-reservation-platform-lab/movie-recommendation-mcp/pull/13)
as the caller pattern.

## 2. Goals

- Coordinate both publisher actions and the PR/local scanner checkout on the reviewed SHA.
- Supply the required prepare token for authenticated canonical-main resolution.
- Protect caller wiring, permissions, component identity, and publication/security boundaries with offline tests.
- Document the complete caller impact, rollout acceptance, and coordinated rollback.

## 3. Non-goals

No application behavior, Docker/dependency, vulnerability exemption, evidence schema,
unrelated action, permission, secret, AWS, environment, or deployment changes. Do not
merge, dispatch workflows, admit artifacts, copy images to ECR, or change GitHub settings.

## 4. Current State

Freshly fetched `origin/main` is `f04acb0859a323a70d62c73236b145b3221cbcec`.
The preserved main checkout is clean; implementation uses a separate worktree.
`.github/workflows/ci.yml` pins `prepare-container-candidate`, `container-evidence`,
and the PR-security tooling checkout to `bb40579c285df0b581c48b10f9b34574d5c78639`.
Prepare does not yet receive a token. Publication already has `contents: read`,
`packages: write`, `id-token: write`, and `attestations: write`, and is guarded to
pushes on this repository's `main`. PR/non-canonical runs build and scan the production
image with a step-scoped `GH_TOKEN`. Evidence is v1alpha3 for component `reservation-mcp`.
`automation/tests/test_release_contract.py` already checks shared-pin coordination and
most publication and PR scanning boundaries.

Actions PR #18 replaces anonymous canonical-main resolution with one bounded authenticated
GitHub API lookup. It also hardens bounded legacy report reads, error sanitization, and
scanner cleanup. The canary changed only the three pins, prepare input, caller contract
tests, and current documentation; its publication and admission subsequently succeeded.

## 5. Requirements and Assumptions

### Confirmed Requirements

- Use the reviewed full SHA for all three tooling consumers.
- Pass `github-token: ${{ github.token }}` to prepare using existing `contents: read`.
- Preserve v1alpha3, component identity, permissions, exact main-push-only publication,
  PR-time production-image scanning, and the absence of `pull_request_target`.
- Keep the producer free of environment reader-app credentials and deployment authority.

### Assumptions

- The successful public canary establishes caller shape, but not universal private-repo access.
- Existing job IDs and component profiles remain compatible with the reviewed release.

### Open Questions

None for implementation. Live authenticated prepare and canonical publication cannot be
exercised on a PR and remain post-merge acceptance checks.

## 6. Proposed Design

Change the three reviewed tooling pins atomically and add the token only to the prepare
step. Introduce one reviewed-SHA constant and a step extractor in the automation tests,
then assert the exact prepare input, coordinated pins, exact publish permissions, exact
canonical guard, and existing PR security authority. Update current README references and
link the earlier security plan to this adoption plan without rewriting historical scan
records. This is preferred because it matches the proven canary and stays independently
revertible.

## 7. Alternatives Considered

### Alternative A: Update prepare only

- Pros: Smallest text diff.
- Cons: Leaves publication evidence and PR/local scanning on older failure handling.
- Decision: Rejected because the reviewed migration requires coordinated pins.

### Alternative B: Coordinated canary-pattern adoption

- Pros: Keeps all security tooling on one reviewed implementation and has a validated caller pattern.
- Cons: Canonical prepare/publication still needs post-merge live acceptance.
- Decision: Selected.

## 8. API / Interface Changes

The CI caller now supplies prepare's required `github-token` input. Application and MCP
interfaces are unchanged. Prepare fails closed before outputs if authentication, canonical
main lookup, response validation, or exact `GITHUB_SHA` matching fails.

## 9. Data Model / Persistence Changes

None. Candidate evidence remains v1alpha3 with the existing four-file package and component identity.

## 10. Security, Privacy, and Abuse Considerations

Use only `${{ github.token }}` and retain the existing job permissions; passing the token
does not narrow its authority. Do not print it, add secrets, use environment reader-app
credentials, persist checkout credentials, add `pull_request_target`, or grant PR jobs write
authority. The new release's bounded error/report handling and scanner cleanup arrive only
through the immutable shared pin.

## 11. Performance, Scalability, and Reliability Considerations

Prepare adds one authenticated, bounded canonical-main API lookup with no retry, redirect,
or anonymous fallback. Failures stop publication before image push. Existing scanner and
central-policy dependencies, job timeouts, concurrency, and main-run non-cancellation remain unchanged.

## 12. Implementation Steps

1. Update `.github/workflows/ci.yml`.
   - Change: Replace the three reviewed pins and add the prepare token input.
   - Notes: Preserve all other workflow behavior and authority.
   - Verification: Contract tests and focused diff inspection.
2. Strengthen `automation/tests/test_release_contract.py`.
   - Change: Assert exact reviewed pins, prepare token scope, permissions, guard, identity, and PR boundaries.
   - Notes: Keep tests offline and behavior-focused.
   - Verification: Run automation tests plus temporary negative mutations.
3. Update `README.md` and `docs/plans/container-security-pr-gate.md`.
   - Change: Point current shared-action/local-tool references at the new SHA and explain impact, acceptance, and rollback.
   - Notes: Preserve historical scan revision records.
   - Verification: Search current references and review Markdown diff.
4. Validate and review.
   - Change: Run repository-prescribed frozen checks and read-only security/maintainability reviews.
   - Verification: Record results in the PR without sensitive local diagnostics.
5. Publish the review branch.
   - Change: Commit with `[ai]`, push, and open one `[ai]` PR closing issue #11.
   - Verification: Observe ordinary PR CI; do not merge or dispatch workflows.

## 13. Testing Strategy

Run `uv sync --frozen`, frozen pytest for runtime and automation tests, Ruff lint and
format checks, compileall for `src tests automation`, and working/staged/branch diff checks.
Use in-memory negative workflow mutations to confirm missing token, pin drift, broadened
permissions, altered component identity, or PR-enabled publication are rejected.

## 14. Rollout / Migration Plan

After an authorized merge, identify the new CI run triggered by the merge commit's canonical
`main` push. Require the complete run and `publish immutable GHCR image` job to succeed, then
admit that exact new run ID through the environments workflow under separate authorization.
Do not reuse historical producer runs. Roll back by reverting all three tooling pins and the
prepare token input together, with their matching tests and current documentation.

## 15. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
| --- | ---: | ---: | --- |
| Missing or misplaced token input | Publication fails closed | Low | Step-scoped exact contract test |
| Tooling pin drift | Inconsistent security behavior | Low | Assert all three exact reviewed SHAs |
| Permission or event-boundary broadening | Excess workflow authority | Low | Assert exact publish permissions and guard plus PR read-only job |
| PR success overstated as publication acceptance | Unsafe rollout decision | Medium | Document PR/live acceptance separation |
| Private repository incompatibility | Post-merge publication failure | Unknown | One producer at a time; stop and diagnose without widening authority |

## 16. Done Criteria

- One issue, branch, commit, and PR cover only this repository's migration.
- Exact pins, token, documentation, and tests are updated without unrelated changes.
- Offline checks and required read-only reviews pass.
- Ordinary PR CI is observed and attributable failures are corrected.
- Live publication/admission remains explicitly unperformed.

## 17. Review Checklist

- [x] Requirements, non-goals, existing conventions, and alternatives inspected.
- [x] Security, reliability, validation, rollout, and rollback specified.
- [x] Implementation steps and affected files are explicit.
- [x] Final diff and checks reviewed before PR handoff.

Validation on 2026-09-15: frozen dependency sync passed; 24 runtime and automation
tests passed; Ruff lint and format checks passed; compileall and diff checks passed.
Seven in-memory negative mutations confirmed rejection of a missing prepare token,
drift in each coordinated pin, broadened publishing contents permission, PR-enabled
publication, and component identity drift. A bounded security and maintainability
self-review found no material issue. Independent repository-prescribed review is
coordinated separately because all agent slots were occupied. Hosted PR checks and
post-merge canonical acceptance remain separate.

## 18. Handoff Prompt for Implementation Agent

```text
Implement docs/plans/authenticated-prepare-adoption.md on issue #11's isolated branch.
Change only the coordinated tooling pins, prepare token input, caller contract tests,
current documentation, and this plan. Preserve every stated boundary. Run all commands
from section 13, request security and maintainability review with file/line evidence,
then commit and open the authorized PR without merging or dispatching workflows.
```
