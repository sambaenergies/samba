# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""samba_service.models -- Pydantic request/response models for the SAMBA REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from samba.run_result.contracts import KpiSummary, SizingRow
from samba_service.jobs import JobStatus

# The request ``scenario`` stays a permissive mapping (so a bad scenario yields a
# structured 200/422 body, not a generic request-shape rejection); this advertises
# the real shape in the OpenAPI contract without constraining the field.
_SCENARIO_FIELD_DESCRIPTION = (
    "Scenario mapping with the same structure as a scenario YAML file "
    "(schema_version, project, location, load, components, tariff, ...). Validated "
    "against the SAMBA Scenario model; see scenario.schema.json for the full shape."
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Shared envelope for every non-2xx response.

    Attributes
    ----------
    detail:
        Human-readable summary of the failure (the FastAPI default error key).
    errors:
        Optional per-item failure lines. For scenario-validation failures this
        is ''ScenarioValidationError.format_errors().splitlines()'' -- the **same
        list** ''POST /api/v1/validate'' returns in its 200 body for the same
        input -- so a client can render field errors identically regardless of
        which endpoint rejected the scenario. ''None'' for errors that have no
        line-level breakdown (404 / 409 / 401 / generic 400).
    """

    detail: str
    errors: list[str] | None = None


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

    scenario: dict[str, Any] = Field(description=_SCENARIO_FIELD_DESCRIPTION)


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
    """Response body for ''GET /health'' (public, unversioned liveness probe).

    Attributes
    ----------
    status:
        Always ''"ok"'' when the service is running.
    version:
        Installed ''samba-core'' package version string. **Display only** — do not
        key API compatibility off it.
    api_version:
        SemVer of the HTTP API surface (equals the OpenAPI ''info.version''); the
        value an external client checks for compatibility. From
        :data:'samba_service._contract.API_VERSION'.
    contract_version:
        Version of the published data/schema contract (OpenAPI + companion JSON
        Schemas) the client generated its types from. From
        :data:'samba_service._contract.CONTRACT_VERSION'.
    capabilities:
        Stable advertised feature flags the client may branch on
        (:data:'samba_service._contract.CAPABILITIES').
    solver:
        Configured solver name (from :attr:'~samba_service.config.ServiceConfig.solver').
    solver_ready:
        ''True'' when the configured solver binary/package is importable.
    active_jobs:
        Number of jobs currently in ''PENDING'' or ''RUNNING'' state.

    The three version axes (samba-core package, API/contract, and the OpenAPI
    spec version owned by FastAPI) are documented in
    :mod:'samba_service._contract'.
    """

    status: Literal["ok"] = "ok"
    version: str
    api_version: str
    contract_version: str
    capabilities: list[str]
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

    scenario: dict[str, Any] = Field(description=_SCENARIO_FIELD_DESCRIPTION)
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
    status: Literal["pending"] = "pending"
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
        Typed :class:'~samba.run_result.contracts.KpiSummary'.  Present only when
        ''status == "completed"''.  Degraded to ''None'' (with a logged warning)
        if a persisted legacy row's stored KPIs no longer match the contract.
    sizing:
        List of typed :class:'~samba.run_result.contracts.SizingRow'.  Present
        only when ''status == "completed"''; degraded as above on legacy rows.
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
    kpis: KpiSummary | None = None
    sizing: list[SizingRow] | None = None
    artifacts: list[str] = []
    error: str | None = None
    solve_time_s: float | None = None
