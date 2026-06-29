# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""samba_service.app -- FastAPI application for the SAMBA REST API (v2).

Endpoints
---------

Public (no auth required):
  GET  /health                                  Liveness / readiness probe.
  GET  /docs                                    Swagger UI.
  GET  /openapi.json                            Raw OpenAPI 3.1 schema.

Protected (require ''X-API-Key'' when ''SAMBA_API_KEY'' env var is set):
  POST /api/v1/validate                         Validate a scenario dict.
  POST /api/v1/jobs                             Submit an async solve job.
  GET  /api/v1/jobs                             List all jobs.
  GET  /api/v1/jobs/{run_id}                    Poll a single job.
  GET  /api/v1/jobs/{run_id}/artifacts/{file}   Download a result artifact.
  DELETE /api/v1/jobs/{run_id}                  Delete a job record.

Security
--------
When ''SAMBA_API_KEY'' is unset (default), all requests pass without
authentication -- suitable for localhost or trusted-network deployments.
When set, every protected request must carry a matching ''X-API-Key'' header.

CORS
----
Configured via ''SAMBA_CORS_ORIGINS'' (comma-separated, default: ''*'').
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from samba.run_result.contracts import KpiSummary, SizingRow
from samba_service import jobs as _jobs
from samba_service._contract import API_VERSION, CAPABILITIES, CONTRACT_VERSION
from samba_service.auth import verify_api_key
from samba_service.config import config
from samba_service.jobs import Job, JobStatus, generate_run_id, store, submit_job
from samba_service.models import (
    ErrorResponse,
    HealthResponse,
    JobStatusResponse,
    JobSubmitRequest,
    JobSubmitResponse,
    ValidateRequest,
    ValidateResponse,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed artifact filenames (path-traversal whitelist)
# ---------------------------------------------------------------------------

_ALLOWED_ARTIFACTS: frozenset[str] = frozenset(
    [
        "scenario.yaml",
        "metadata.json",
        "kpis.json",
        "sizing.csv",
        "dispatch.parquet",
        "dispatch.csv",
        "economics.json",
        "annual_summary.csv",
        "tariff.parquet",
        "solver.log",
    ]
)

# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan handler: initialise executor on startup, shut it down."""
    _jobs.init_executor(config.max_concurrent)
    log.info(
        "SAMBA service started (solver=%s, max_concurrent=%d).",
        config.solver,
        config.max_concurrent,
    )
    yield
    _jobs.shutdown_executor(wait=False)
    log.info("SAMBA service stopped.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SAMBA Service",
    version=API_VERSION,
    description=(
        "Microgrid optimisation REST API wrapping the SAMBA core library.\n\n"
        "**Features:** async job queue, artifact downloads, CORS, optional API key auth.\n\n"
        "**Security notice:** when ''SAMBA_API_KEY'' is unset, no authentication is enforced. "
        "For trusted / local use only unless an auth proxy is in front."
    ),
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=_lifespan,
)

# CORS -- applied before routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------

# Shared OpenAPI ``responses`` documenting that every non-2xx body is an
# :class:`~samba_service.models.ErrorResponse`. Applied uniformly to all routes
# so the published contract carries typed error shapes (consumers generate one
# error type, not per-route guesses).
#
# Descriptions are pinned explicitly rather than left to FastAPI's default, which
# derives them from ``http.HTTPStatus(code).phrase`` -- a Python-stdlib string
# that is NOT stable across interpreter versions (e.g. 422 became "Unprocessable
# Content" in 3.13, was "Unprocessable Entity"). Pinning keeps the exported
# openapi.json byte-identical across the Python test matrix.
_ERROR_DESCRIPTIONS: dict[int, str] = {
    400: "Bad request",
    401: "Unauthorized",
    404: "Not found",
    409: "Conflict",
    422: "Validation error",
    500: "Internal server error",
}
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse, "description": desc}
    for code, desc in _ERROR_DESCRIPTIONS.items()
}
_HEALTH_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"model": ErrorResponse, "description": _ERROR_DESCRIPTIONS[500]},
}


class ScenarioInvalidError(Exception):
    """Raised when a submitted scenario fails Pydantic validation.

    Carries the per-line error list so the handler can return the **same**
    ``errors[]`` that ``POST /api/v1/validate`` reports for the same input.
    """

    def __init__(self, errors: list[str]) -> None:
        super().__init__("Scenario validation failed.")
        self.errors = errors


def _error_body(detail: str, errors: list[str] | None = None) -> dict[str, Any]:
    return ErrorResponse(detail=detail, errors=errors).model_dump()


@app.exception_handler(ScenarioInvalidError)
async def _scenario_invalid_handler(_request: Request, exc: ScenarioInvalidError) -> JSONResponse:
    return JSONResponse(
        status_code=422, content=_error_body("Scenario validation failed.", exc.errors)
    )


@app.exception_handler(RequestValidationError)
async def _request_validation_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Normalise FastAPI's default ``{detail: [..]}`` 422 into the shared envelope."""
    lines = [_format_request_error(e) for e in exc.errors()]
    return JSONResponse(status_code=422, content=_error_body("Request validation failed.", lines))


def _format_request_error(err: dict[str, Any]) -> str:
    loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
    msg = err.get("msg", "invalid")
    return f"{loc}: {msg}" if loc else msg


# ---------------------------------------------------------------------------
# Shared router (prefix + auth dependency applied to all protected endpoints)
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/v1",
    dependencies=[Security(verify_api_key)],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _solver_ready(solver_name: str) -> bool:
    """Return ''True'' when the configured solver is importable / available."""
    if solver_name in ("appsi_highs", "highs"):
        try:
            import highspy  # noqa: F401

            return True
        except ImportError:
            return False
    import shutil

    return shutil.which(solver_name) is not None


def _artifact_list(run_dir: Path) -> list[str]:
    """Return downloadable filenames present in *run_dir*."""
    if not run_dir or not run_dir.is_dir():
        return []
    return sorted(f.name for f in run_dir.iterdir() if f.is_file() and f.name in _ALLOWED_ARTIFACTS)


def _coerce_kpis(run_id: str, raw: dict[str, Any] | None) -> KpiSummary | None:
    """Validate stored KPIs against the contract, degrading a bad row to None.

    Coerce-or-degrade is uniform: a row whose stored KPIs no longer match
    ``KpiSummary`` (e.g. a persisted legacy row from before a contract change)
    is logged and dropped to ``None`` rather than raising, so one bad row can
    never break the whole ``GET /jobs`` list. Live solver output is separately
    and loudly gated against the contract by ``test_artifact_contracts.py``, so
    a genuinely malformed *fresh* result is caught there, not silently shipped.
    """
    if raw is None:
        return None
    try:
        return KpiSummary.model_validate(raw)
    except ValidationError:
        log.warning("Job %s: stored kpis no longer match KpiSummary; degrading to null.", run_id)
        return None


def _coerce_sizing(run_id: str, raw: list[dict[str, Any]] | None) -> list[SizingRow] | None:
    """Validate stored sizing rows against the contract; degrade the field on failure."""
    if raw is None:
        return None
    try:
        return [SizingRow.model_validate(row) for row in raw]
    except ValidationError:
        log.warning("Job %s: stored sizing no longer match SizingRow; degrading to null.", run_id)
        return None


def _job_to_response(job: Job) -> JobStatusResponse:
    """Build a :class:'JobStatusResponse' from a :class:'~samba_service.jobs.Job'."""
    artifacts: list[str] = []
    if job.status == JobStatus.COMPLETED and job.run_dir is not None:
        artifacts = _artifact_list(job.run_dir)
    return JobStatusResponse(
        run_id=job.run_id,
        status=job.status,
        submitted_at=job.submitted_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        kpis=_coerce_kpis(job.run_id, job.kpis),
        sizing=_coerce_sizing(job.run_id, job.sizing),
        artifacts=artifacts,
        error=job.error,
        solve_time_s=job.solve_time_s,
    )


# ---------------------------------------------------------------------------
# GET /health  (no auth -- always public)
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    response_model=HealthResponse,
    operation_id="getHealth",
    summary="Service health check",
    description=(
        "Returns service status, samba-core version, API/contract version, advertised "
        "capabilities, solver availability, and active job count."
    ),
    responses=_HEALTH_ERROR_RESPONSES,
    tags=["meta"],
)
def health() -> HealthResponse:
    """Liveness / readiness probe -- always public, no auth required."""
    from samba._version import __version__ as samba_version

    active = sum(1 for j in store.list_all() if j.status in (JobStatus.PENDING, JobStatus.RUNNING))
    return HealthResponse(
        status="ok",
        version=samba_version,
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        capabilities=CAPABILITIES,
        solver=config.solver,
        solver_ready=_solver_ready(config.solver),
        active_jobs=active,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/validate
# ---------------------------------------------------------------------------


@router.post(
    "/validate",
    response_model=ValidateResponse,
    operation_id="validateScenario",
    summary="Validate a scenario",
    responses=ERROR_RESPONSES,
    tags=["scenarios"],
)
def validate(request: ValidateRequest) -> ValidateResponse:
    """Validate *request.scenario* against the SAMBA Pydantic schema.

    Always returns HTTP 200; check the ''valid'' field in the response.
    """
    from samba.scenario.loader import ScenarioValidationError
    from samba.scenario.models import Scenario

    try:
        Scenario.model_validate(request.scenario)
        return ValidateResponse(valid=True)
    except ValidationError as exc:
        err = ScenarioValidationError(exc)
        return ValidateResponse(valid=False, errors=err.format_errors().splitlines())


# ---------------------------------------------------------------------------
# POST /api/v1/jobs  -- submit async job
# ---------------------------------------------------------------------------


@router.post(
    "/jobs",
    response_model=JobSubmitResponse,
    status_code=202,
    operation_id="submitJob",
    summary="Submit an async optimisation job",
    responses=ERROR_RESPONSES,
    tags=["jobs"],
)
def submit(request: JobSubmitRequest) -> JobSubmitResponse:
    """Validate the scenario dict and enqueue an async solve job.

    Returns HTTP 202 with ''run_id'' immediately.  Poll
    ''GET /api/v1/jobs/{run_id}'' for status.
    """
    from samba.scenario.loader import ScenarioValidationError
    from samba.scenario.models import Scenario

    # Validate scenario before queuing -- fail fast with a 422 whose errors[]
    # is byte-identical to what POST /api/v1/validate returns for the same input.
    try:
        Scenario.model_validate(request.scenario)
    except ValidationError as exc:
        err = ScenarioValidationError(exc)
        raise ScenarioInvalidError(err.format_errors().splitlines()) from exc

    run_id = generate_run_id()
    submit_job(run_id, request.scenario, request.run_dir_name)

    return JobSubmitResponse(
        run_id=run_id,
        poll_url=f"/api/v1/jobs/{run_id}",
    )


# ---------------------------------------------------------------------------
# GET /api/v1/jobs  -- list all jobs
# ---------------------------------------------------------------------------


@router.get(
    "/jobs",
    response_model=list[JobStatusResponse],
    operation_id="listJobs",
    summary="List all jobs",
    responses=ERROR_RESPONSES,
    tags=["jobs"],
)
def list_jobs(
    status: str | None = Query(
        default=None,
        description="Filter by status (pending/running/completed/failed)",
    ),
) -> list[JobStatusResponse]:
    """Return all job records, sorted by submission time descending.

    Use the optional ''?status='' query parameter to filter.
    """
    all_jobs = store.list_all(status_filter=status)
    return [_job_to_response(j) for j in all_jobs]


# ---------------------------------------------------------------------------
# GET /api/v1/jobs/{run_id}  -- poll a single job
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{run_id}",
    response_model=JobStatusResponse,
    operation_id="getJob",
    summary="Poll job status",
    responses=ERROR_RESPONSES,
    tags=["jobs"],
)
def get_job(run_id: str) -> JobStatusResponse:
    """Return the current status of a submitted job."""
    job = store.get(run_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{run_id}' not found.")
    return _job_to_response(job)


# ---------------------------------------------------------------------------
# GET /api/v1/jobs/{run_id}/artifacts/{filename}  -- download artifact
# ---------------------------------------------------------------------------

_ARTIFACT_MEDIA_TYPES: dict[str, str] = {
    ".json": "application/json",
    ".csv": "text/csv",
    ".parquet": "application/octet-stream",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".log": "text/plain",
}


@router.get(
    "/jobs/{run_id}/artifacts/{filename}",
    operation_id="getArtifact",
    summary="Download a result artifact",
    responses=ERROR_RESPONSES,
    tags=["jobs"],
)
def get_artifact(run_id: str, filename: str) -> FileResponse:
    """Stream a result file from the job's artifact directory.

    Allowed filenames: ''scenario.yaml'', ''kpis.json'', ''sizing.csv'',
    ''dispatch.parquet'', ''dispatch.csv'', ''economics.json'',
    ''annual_summary.csv'', ''tariff.parquet'', ''metadata.json'',
    ''solver.log''.

    Returns HTTP 400 on any path-traversal attempt.
    """
    # 1. Look up job
    job = store.get(run_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{run_id}' not found.")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Artifacts unavailable: job is '{job.status.value}', not 'completed'.",
        )
    if job.run_dir is None:
        raise HTTPException(status_code=404, detail="No artifact directory for this job.")

    # 2. Whitelist check
    if filename not in _ALLOWED_ARTIFACTS:
        raise HTTPException(
            status_code=400,
            detail=f"'{filename}' is not a downloadable artifact. "
            f"Allowed: {sorted(_ALLOWED_ARTIFACTS)}",
        )

    # 3. Path-traversal check (belt-and-suspenders)
    resolved_dir = job.run_dir.resolve()
    candidate = (job.run_dir / filename).resolve()
    if candidate.parent != resolved_dir:
        raise HTTPException(status_code=400, detail="Path traversal detected.")

    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"Artifact '{filename}' not found on disk.")

    suffix = Path(filename).suffix.lower()
    media_type = _ARTIFACT_MEDIA_TYPES.get(suffix, "application/octet-stream")
    return FileResponse(path=str(candidate), filename=filename, media_type=media_type)


# ---------------------------------------------------------------------------
# DELETE /api/v1/jobs/{run_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/jobs/{run_id}",
    status_code=204,
    operation_id="deleteJob",
    summary="Delete a job record",
    responses=ERROR_RESPONSES,
    tags=["jobs"],
)
def delete_job(
    run_id: str,
    delete_artifacts: bool = Query(
        default=False,
        alias="delete_artifacts",
        description="Also delete the artifact directory from disk.",
    ),
) -> None:
    """Remove a job from the in-process store.

    Optionally delete the on-disk artifact directory when
    ''?delete_artifacts=true''.  Returns HTTP 204 on success.
    """
    job = store.get(run_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{run_id}' not found.")

    if delete_artifacts and job.run_dir is not None and job.run_dir.exists():
        import shutil

        shutil.rmtree(job.run_dir, ignore_errors=True)
        log.info("Deleted artifact directory: %s", job.run_dir)

    store.remove(run_id)


# ---------------------------------------------------------------------------
# Mount router
# ---------------------------------------------------------------------------

app.include_router(router)
