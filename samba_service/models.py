# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""samba_service.models -- Pydantic request/response models for the SAMBA REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from samba_service.jobs import JobStatus

# ---------------------------------------------------------------------------
# Validate endpoint
# ---------------------------------------------------------------------------


class ValidateRequest(BaseModel):
    """Request body for ''POST /api/v1/validate''.

    Attributes
    ----------
    scenario:
        Raw scenario mapping to validate against the SAMBA schema.
    """

    scenario: dict[str, Any]


class ValidateResponse(BaseModel):
    """Response body for ''POST /api/v1/validate''.

    Attributes
    ----------
    valid:
        ''True'' when the scenario passes all schema checks.
    errors:
        List of ''"field.path: message"'' strings describing every validation
        failure.  Empty when ''valid is True''.
    """

    valid: bool
    errors: list[str] = []


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Response body for ''GET /api/v1/health''.

    Attributes
    ----------
    status:
        Always ''"ok"'' when the service is running.
    version:
        Installed ''samba-core'' package version string.
    solver:
        Configured solver name (from :attr:'~samba_service.config.ServiceConfig.solver').
    solver_ready:
        ''True'' when the configured solver binary/package is importable.
    active_jobs:
        Number of jobs currently in ''PENDING'' or ''RUNNING'' state.
    """

    status: Literal["ok"] = "ok"
    version: str
    solver: str
    solver_ready: bool
    active_jobs: int = 0


# ---------------------------------------------------------------------------
# Job submit / poll / list
# ---------------------------------------------------------------------------


class JobSubmitRequest(BaseModel):
    """Request body for ''POST /api/v1/jobs''.

    Attributes
    ----------
    scenario:
        Raw scenario mapping with the same structure as a scenario YAML file
        (''schema_version'', ''project'', ''load'', ''components'', etc.).
    run_dir_name:
        Optional custom stem for the run output directory.  When ''None'',
        the service creates a subdirectory named by the job's ''run_id''.
    """

    scenario: dict[str, Any]
    run_dir_name: str | None = None


class JobSubmitResponse(BaseModel):
    """Response body for ''POST /api/v1/jobs'' (HTTP 202 Accepted).

    Attributes
    ----------
    run_id:
        UUID4 string identifying the submitted job.
    status:
        Initial status -- always ''"pending"'' immediately after submission.
    poll_url:
        Relative URL for polling job state:
        ''/api/v1/jobs/{run_id}''.
    """

    run_id: str
    status: str = "pending"
    poll_url: str


class JobStatusResponse(BaseModel):
    """Response body for ''GET /api/v1/jobs/{run_id}''.

    Attributes
    ----------
    run_id:
        UUID4 job identifier.
    status:
        Current :class:'~samba_service.jobs.JobStatus'.
    submitted_at:
        UTC timestamp of job submission.
    started_at:
        UTC timestamp when the solver thread picked up the job, or ''None''.
    completed_at:
        UTC timestamp of job completion (success or failure), or ''None''.
    kpis:
        KPI dict (28 fields).  Present only when ''status == "completed"''.
    sizing:
        List of sizing records.  Present only when ''status == "completed"''.
    artifacts:
        List of downloadable filenames available under
        ''GET /api/v1/jobs/{run_id}/artifacts/{filename}''.
        Populated only when ''status == "completed"''.
    error:
        Human-readable error description when ''status == "failed"''.
    """

    run_id: str
    status: JobStatus
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    kpis: dict[str, Any] | None = None
    sizing: list[dict[str, Any]] | None = None
    artifacts: list[str] = []
    error: str | None = None
    solve_time_s: float | None = None


# ---------------------------------------------------------------------------
# Kept for backward compatibility with v1 synchronous test_service.py
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    """[Deprecated - v1 only] Request body for ''POST /api/v1/run''."""

    scenario: dict[str, Any]
    run_dir_name: str | None = None


class RunResponse(BaseModel):
    """[Deprecated - v1 only] Response body for ''POST /api/v1/run''."""

    status: Literal["ok", "infeasible", "error"]
    run_dir: str | None = None
    kpis: dict[str, Any] | None = None
    sizing: list[dict[str, Any]] | None = None
    error: str | None = None
    error_code: int | None = None
