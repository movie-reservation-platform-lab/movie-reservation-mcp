from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
REVIEWED_ACTIONS_SHA = "036531133bcefd454b5afc0eb55f8ba0328901ea"


def test_production_image_is_locked_non_root_and_offline_safe() -> None:
    production_stage = dockerfile_stage("prod")

    assert "ghcr.io/astral-sh/uv:0.12.3" in DOCKERFILE
    assert "FASTMCP_CHECK_FOR_UPDATES=off" in DOCKERFILE
    assert "UV_PYTHON_DOWNLOADS=never" in DOCKERFILE
    assert "FROM python-runtime AS prod" in DOCKERFILE
    assert "useradd -r -u 10001 appuser" in production_stage
    assert "USER appuser" in production_stage
    assert "EXPOSE 8091" in production_stage
    assert "http://127.0.0.1:8091/health" in production_stage
    assert "curl" not in production_stage
    assert "COPY --from=uv" not in production_stage
    assert "COPY --from=build --chown=10001:10001 /venv /venv" in production_stage
    assert "ca-certificates tini perl-base" in production_stage


def test_development_image_keeps_tooling_outside_production() -> None:
    development_stage = dockerfile_stage("development")

    assert "FROM build-tools AS development" in DOCKERFILE
    assert "curl" in development_stage
    assert "uv sync --no-install-project --frozen" in development_stage
    assert "uv sync --frozen" in development_stage
    assert "COPY tests /app/tests" in development_stage
    assert "COPY automation /app/automation" in development_stage
    assert "COPY Dockerfile /app/Dockerfile" in development_stage
    assert "COPY .github/workflows/ci.yml /app/.github/workflows/ci.yml" in development_stage
    assert '["uv", "run", "--frozen", "--no-sync", "movie-reservation-mcp"]' in development_stage


def test_publication_is_main_only_gated_and_attested() -> None:
    publish_job = workflow_job("publish-image")

    assert re.findall(r"^    if: (.+)$", publish_job, re.MULTILINE) == [
        (
            "github.event_name == 'push' && github.ref == 'refs/heads/main' && "
            "github.repository == 'movie-reservation-platform-lab/movie-reservation-mcp'"
        )
    ]
    assert "- quality" in publish_job
    assert "- contract-tests" in publish_job
    assert "- automation-tests" in publish_job
    assert "- container-smoke" in publish_job
    assert re.search(r"^    permissions:\n((?:      .+\n)+)", publish_job, re.MULTILINE).group(1) == (
        "      contents: read\n      packages: write\n      id-token: write\n      attestations: write\n"
    )
    assert "platforms: linux/amd64" in publish_job
    assert "provenance: false" in publish_job
    assert "/actions/container-evidence@" in publish_job
    assert "digest: ${{ steps.build.outputs.digest }}" in publish_job
    assert "pull_request_target:" not in WORKFLOW


def test_repository_automation_is_separate_from_contract_tests() -> None:
    contract_job = workflow_job("contract-tests")
    automation_job = workflow_job("automation-tests")

    assert "pytest tests" in contract_job
    assert "pytest automation/tests" not in contract_job
    assert "pytest automation/tests" in automation_job
    assert "pytest tests" not in automation_job


def workflow_job(name: str) -> str:
    lines = WORKFLOW.splitlines()
    start = lines.index(f"  {name}:")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith("  ") and lines[index].endswith(":") and not lines[index].startswith("    ")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def dockerfile_stage(name: str) -> str:
    lines = DOCKERFILE.splitlines()
    start = next(index for index, line in enumerate(lines) if line.endswith(f" AS {name}"))
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("FROM ")), len(lines))
    return "\n".join(lines[start:end])


def workflow_step(job: str, name: str) -> str:
    match = re.search(rf"^      - name: {re.escape(name)}\n.*?(?=^      - name:|\Z)", job, re.MULTILINE | re.DOTALL)
    assert match is not None, f"Missing workflow step: {name}"
    return match.group()


def test_prepare_receives_explicit_caller_token() -> None:
    prepare_step = workflow_step(workflow_job("publish-image"), "Prepare canonical candidate")

    assert f"/actions/prepare-container-candidate@{REVIEWED_ACTIONS_SHA}" in prepare_step
    assert "        with:\n          component: reservation-mcp\n" in prepare_step
    assert "          github-token: ${{ github.token }}\n" in prepare_step


def test_container_evidence_receives_exact_candidate_inputs() -> None:
    evidence_step = workflow_step(workflow_job("publish-image"), "Attest and publish security evidence")

    assert f"/actions/container-evidence@{REVIEWED_ACTIONS_SHA}" in evidence_step
    assert evidence_step.endswith(
        "        with:\n"
        "          evidence-version: v1alpha3\n"
        "          component: reservation-mcp\n"
        "          digest: ${{ steps.build.outputs.digest }}\n"
        "          github-token: ${{ github.token }}"
    )


def test_producer_workflow_does_not_use_environment_reader_app_credentials() -> None:
    assert "actions/create-github-app-token" not in WORKFLOW
    assert "EVIDENCE_READER_APP_" not in WORKFLOW
    assert "EXEMPTION_POLICY_READER_APP_" not in WORKFLOW


def test_shared_evidence_has_pinned_identity_and_precedes_no_quality_gate() -> None:
    publish_job = workflow_job("publish-image")
    assert "github.repository == 'movie-reservation-platform-lab/movie-reservation-mcp'" in publish_job
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in WORKFLOW
    assert "persist-credentials: false" in publish_job
    assert "component: reservation-mcp" in publish_job
    assert "tags: ${{ steps.candidate.outputs.image_ref }}:${{ steps.candidate.outputs.tag }}" in publish_job
    assert publish_job.index("/actions/prepare-container-candidate@") < publish_job.index("docker/login-action@")
    assert publish_job.index("docker/build-push-action@") < publish_job.index("/actions/container-evidence@")
    references = re.findall(r"uses: (\S+)", WORKFLOW)
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference) for reference in references)
    shared_pins = [
        reference.split("@")[1] for reference in references if "/movie-platform-actions/actions/" in reference
    ]
    assert shared_pins == [REVIEWED_ACTIONS_SHA, REVIEWED_ACTIONS_SHA]
    tooling_checkout = workflow_step(
        workflow_job("container-security-check"), "Check out reviewed shared security tooling"
    )
    assert f"          ref: {REVIEWED_ACTIONS_SHA}\n" in tooling_checkout
    assert "repository: movie-reservation-platform-lab/movie-platform-actions" in tooling_checkout
    assert "evidence-version: v1alpha3" in publish_job
    assert "aws-actions/" not in WORKFLOW


def test_pr_security_gate_uses_shared_policy_without_publication_permissions() -> None:
    security_job = workflow_job("container-security-check")

    assert "pull_request:" in WORKFLOW
    assert "github.event_name != 'push' || github.ref != 'refs/heads/main'" in security_job
    assert "github.repository != 'movie-reservation-platform-lab/movie-reservation-mcp'" in security_job
    assert "- quality" in security_job
    assert "- automation-tests" in security_job
    assert "permissions:\n      contents: read" in security_job
    assert ": write" not in security_job
    assert "docker/login-action" not in security_job
    assert "push: true" not in security_job
    assert security_job.count("persist-credentials: false") == 2
    assert "node-version: '24'" in security_job
    assert "--platform linux/amd64 --target prod" in security_job
    assert "node .platform-actions/local-tools/container-security/lib/scan.mjs" in security_job
    assert "--evidence-version v1alpha3 --component reservation-mcp" in security_job
    assert security_job.count("GH_TOKEN:") == 1
    assert security_job.index("GH_TOKEN:") > security_job.index("run: docker build")
    assert "continue-on-error" not in security_job
    assert "|| true" not in security_job
    assert "aquasecurity/trivy-action" not in security_job


def test_pr_security_diagnostics_survive_policy_failure_and_are_not_candidate_evidence() -> None:
    security_job = workflow_job("container-security-check")

    assert security_job.index("lib/scan.mjs") < security_job.index("actions/upload-artifact@")
    assert "if: ${{ !cancelled() }}" in security_job
    assert '--output-dir "$RUNNER_TEMP/reservation-mcp-pr-security"' in security_job
    assert "path: ${{ runner.temp }}/reservation-mcp-pr-security/" in security_job
    assert "name: reservation-mcp-pr-vulnerability-report-" in security_job
    assert "if-no-files-found: error" in security_job
    assert "retention-days: 14" in security_job
    assert "attest-build-provenance" not in security_job
    assert "container-evidence@" not in security_job


def test_production_smoke_exercises_installed_mcp_and_retains_failure_logs() -> None:
    smoke_job = workflow_job("container-smoke")

    assert "--platform linux/amd64 --target prod" in smoke_job
    assert "docker exec -i movie-reservation-mcp python - < automation/container_smoke.py" in smoke_job
    assert "if: failure()\n        run: docker logs movie-reservation-mcp" in smoke_job
