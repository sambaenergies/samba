"""Tests for the SAMBA v2 REST service (async job API).

Fast tests (no solver, <1 s each):
  TestHealthV2, TestDocsV2, TestAuthDisabled, TestAuthEnabled,
  TestValidateV2, TestJobSubmitFast, TestJobGet, TestJobList,
  TestJobArtifacts, TestJobDelete, TestJobListStatusFilter

Integration tests (real solver, ~5-15 min, marked ``slow`` + ``integration``):
  TestJobFullLifecycle

Run only fast tests::

    pytest tests/unit/test_service_v2.py -m "not slow" -v

Run all v2 service tests (including solver)::

    pytest tests/unit/test_service_v2.py -v
"""

from __future__ import annotations

import importlib.util
import json
import time
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from samba_service.app import app
from samba_service.jobs import Job, JobStatus, store

# ---------------------------------------------------------------------------
# Solver availability guard
# ---------------------------------------------------------------------------

_highs_available = importlib.util.find_spec("highspy") is not None
skip_no_solver = pytest.mark.skipif(
    not _highs_available,
    reason="highspy not installed — run 'pip install highspy' or 'pip install -e .'",
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_G01_DIR = Path(__file__).parent.parent / "goldens" / "g01_grid_pv_batt"

# ---------------------------------------------------------------------------
# Shared minimal valid scenario (all required fields; no CSV existence check
# during schema validation)
# ---------------------------------------------------------------------------

_MINIMAL_VALID: dict[str, Any] = {
    "schema_version": "1.0",
    "project": {
        "name": "svc-v2-test",
        "lifetime_years": 10,
        "discount_rate_nominal": 0.08,
        "inflation_rate": 0.02,
    },
    "location": {
        "latitude": 37.77,
        "longitude": -122.42,
        "timezone": "America/Los_Angeles",
    },
    "weather": {
        "source": "csv",
        "csv_path": "dummy.csv",
    },
    "load": {"source": "generic_annual_total", "annual_kwh": 17520.0},
    "components": {
        "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
        "grid": {"capacity_kw": 100.0},
    },
    "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.15}},
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Module-scoped TestClient — runs lifespan (executor init/shutdown)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_client() -> Generator[TestClient, None, None]:
    """Client fixture with API key auth enabled; resets after test."""
    from samba_service.config import config as svc_config

    original_key = svc_config.api_key
    svc_config.api_key = "super-secret-key"
    # Reconstruct auth module state so verify_api_key reads new config value
    # (config is a singleton, verify_api_key reads config.api_key at call-time)
    with TestClient(app) as c:
        yield c
    svc_config.api_key = original_key


@pytest.fixture()
def completed_job(tmp_path: Path) -> Generator[Job, None, None]:
    """Pre-populate the job store with a COMPLETED job backed by disk files.

    Yields the :class:`~samba_service.jobs.Job` and cleans up the store entry
    after the test.
    """
    run_dir = tmp_path / "run_test_completed"
    run_dir.mkdir()

    kpis = {"npc": 123456.0, "lcoe": 0.42, "lcos": 0.18}
    sizing = [{"component": "pv", "capacity_kw": 10.0}]
    (run_dir / "kpis.json").write_text(json.dumps(kpis), encoding="utf-8")
    (run_dir / "sizing.csv").write_text("component,capacity_kw\npv,10.0\n", encoding="utf-8")

    job = Job(
        run_id="completed-fixture-id",
        status=JobStatus.COMPLETED,
        submitted_at=datetime.now(UTC),
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        run_dir=run_dir,
        kpis=kpis,
        sizing=sizing,
    )
    store._jobs["completed-fixture-id"] = job
    yield job
    store._jobs.pop("completed-fixture-id", None)


@pytest.fixture()
def pending_job() -> Generator[Job, None, None]:
    """Pre-populate store with a PENDING job (no run_dir)."""
    job = Job(
        run_id="pending-fixture-id",
        status=JobStatus.PENDING,
        submitted_at=datetime.now(UTC),
    )
    store._jobs["pending-fixture-id"] = job
    yield job
    store._jobs.pop("pending-fixture-id", None)


# ---------------------------------------------------------------------------
# TestHealthV2
# ---------------------------------------------------------------------------


class TestHealthV2:
    """Public /health endpoint — always reachable without auth."""

    def test_health_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_status_ok(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_has_version(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert "version" in data
        assert isinstance(data["version"], str)

    def test_health_has_solver_fields(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert "solver" in data
        assert "solver_ready" in data
        assert isinstance(data["solver_ready"], bool)

    def test_health_has_active_jobs(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert "active_jobs" in data
        assert isinstance(data["active_jobs"], int)
        assert data["active_jobs"] >= 0

    def test_health_reports_api_version_from_constant(self, client: TestClient) -> None:
        from samba_service._contract import API_VERSION

        data = client.get("/health").json()
        assert data["api_version"] == API_VERSION

    def test_health_reports_contract_version_and_capabilities(self, client: TestClient) -> None:
        from samba_service._contract import CAPABILITIES, CONTRACT_VERSION

        data = client.get("/health").json()
        assert data["contract_version"] == CONTRACT_VERSION
        assert data["capabilities"] == CAPABILITIES
        assert isinstance(data["capabilities"], list)


# ---------------------------------------------------------------------------
# TestDocsV2
# ---------------------------------------------------------------------------


class TestDocsV2:
    """OpenAPI docs endpoints."""

    def test_swagger_ui_returns_200(self, client: TestClient) -> None:
        assert client.get("/docs").status_code == 200

    def test_openapi_json_returns_200(self, client: TestClient) -> None:
        assert client.get("/openapi.json").status_code == 200

    def test_openapi_has_jobs_path(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/v1/jobs" in paths

    def test_openapi_has_validate_path(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/v1/validate" in paths

    def test_openapi_has_health_path(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/health" in paths

    def test_openapi_version_matches_api_version_constant(self, client: TestClient) -> None:
        from samba_service._contract import API_VERSION

        info = client.get("/openapi.json").json()["info"]
        assert info["version"] == API_VERSION


# ---------------------------------------------------------------------------
# TestErrorContractV2 — typed error envelope + stable operation_ids
# ---------------------------------------------------------------------------


class TestErrorContractV2:
    """The error surface is part of the typed, stable contract."""

    _EXPECTED_OPERATION_IDS = {
        ("/health", "get"): "getHealth",
        ("/api/v1/validate", "post"): "validateScenario",
        ("/api/v1/jobs", "post"): "submitJob",
        ("/api/v1/jobs", "get"): "listJobs",
        ("/api/v1/jobs/{run_id}", "get"): "getJob",
        ("/api/v1/jobs/{run_id}/artifacts/{filename}", "get"): "getArtifact",
        ("/api/v1/jobs/{run_id}", "delete"): "deleteJob",
    }

    def test_routes_have_explicit_operation_ids(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        for (path, method), op_id in self._EXPECTED_OPERATION_IDS.items():
            assert paths[path][method]["operationId"] == op_id

    def test_every_route_documents_error_envelope(self, client: TestClient) -> None:
        """Every protected route documents the 6 error codes; /health documents 500.

        All non-2xx bodies must reference the shared ErrorResponse model.
        """
        paths = client.get("/openapi.json").json()["paths"]

        def assert_error_ref(responses: dict, code: str, op: str) -> None:
            assert code in responses, f"{op} missing documented {code}"
            ref = responses[code]["content"]["application/json"]["schema"]["$ref"]
            assert ref.endswith("/ErrorResponse"), f"{op} {code} is not ErrorResponse"

        for (path, method), op_id in self._EXPECTED_OPERATION_IDS.items():
            responses = paths[path][method]["responses"]
            codes = ("500",) if path == "/health" else ("400", "401", "404", "409", "422", "500")
            for code in codes:
                assert_error_ref(responses, code, op_id)

    def test_validate_200_and_submit_422_share_error_lines(self, client: TestClient) -> None:
        """The same malformed scenario yields a byte-identical errors[] list."""
        bad = {k: v for k, v in _MINIMAL_VALID.items() if k != "load"}

        validate_resp = client.post("/api/v1/validate", json={"scenario": bad})
        assert validate_resp.status_code == 200
        validate_errors = validate_resp.json()["errors"]

        submit_resp = client.post("/api/v1/jobs", json={"scenario": bad})
        assert submit_resp.status_code == 422
        submit_body = submit_resp.json()
        assert submit_body["errors"] == validate_errors  # byte-identical list
        assert isinstance(submit_body["detail"], str)

    def test_404_matches_error_envelope(self, client: TestClient) -> None:
        body = client.get("/api/v1/jobs/does-not-exist").json()
        assert isinstance(body["detail"], str)
        assert body.get("errors") is None

    def test_request_validation_422_uses_error_envelope(self, client: TestClient) -> None:
        body = client.post("/api/v1/jobs", json={}).json()
        assert isinstance(body["detail"], str)
        assert isinstance(body["errors"], list) and len(body["errors"]) > 0

    def test_401_matches_error_envelope(self, auth_client: TestClient) -> None:
        body = auth_client.get("/api/v1/jobs").json()
        assert isinstance(body["detail"], str)


# ---------------------------------------------------------------------------
# TestAuthDisabled — default: no SAMBA_API_KEY set
# ---------------------------------------------------------------------------


class TestAuthDisabled:
    """When api_key is None (default), all protected endpoints pass."""

    def test_validate_no_key_passes(self, client: TestClient) -> None:
        resp = client.post("/api/v1/validate", json={"scenario": _MINIMAL_VALID})
        assert resp.status_code == 200

    def test_list_jobs_no_key_passes(self, client: TestClient) -> None:
        resp = client.get("/api/v1/jobs")
        assert resp.status_code == 200

    def test_health_no_key_passes(self, client: TestClient) -> None:
        # Health is always public
        assert client.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# TestAuthEnabled — SAMBA_API_KEY set to "super-secret-key"
# ---------------------------------------------------------------------------


class TestAuthEnabled:
    """When api_key is configured, protected routes enforce it."""

    def test_no_key_header_returns_401(self, auth_client: TestClient) -> None:
        resp = auth_client.get("/api/v1/jobs")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, auth_client: TestClient) -> None:
        resp = auth_client.get("/api/v1/jobs", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_correct_key_passes(self, auth_client: TestClient) -> None:
        resp = auth_client.get("/api/v1/jobs", headers={"X-API-Key": "super-secret-key"})
        assert resp.status_code == 200

    def test_health_is_public_even_with_auth_enabled(self, auth_client: TestClient) -> None:
        # /health must NOT be behind the auth router
        resp = auth_client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TestValidateV2
# ---------------------------------------------------------------------------


class TestValidateV2:
    """POST /api/v1/validate — fast schema checks, no solver."""

    def test_valid_scenario_returns_valid_true(self, client: TestClient) -> None:
        resp = client.post("/api/v1/validate", json={"scenario": _MINIMAL_VALID})
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_missing_load_returns_invalid(self, client: TestClient) -> None:
        bad = {k: v for k, v in _MINIMAL_VALID.items() if k != "load"}
        resp = client.post("/api/v1/validate", json={"scenario": bad})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "errors" in data and len(data["errors"]) > 0

    def test_invalid_latitude_returns_invalid(self, client: TestClient) -> None:
        bad = dict(_MINIMAL_VALID)
        bad["location"] = {"latitude": 999.0, "longitude": 0.0, "timezone": "UTC"}
        resp = client.post("/api/v1/validate", json={"scenario": bad})
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_empty_body_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/validate", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestJobSubmitFast — monkeypatched: no real solver, fast
# ---------------------------------------------------------------------------


class TestJobSubmitFast:
    """POST /api/v1/jobs — submit path (solver monkeypatched away)."""

    def _mock_submit(
        self, run_id: str, scenario_dict: dict[str, Any], run_dir_name: str | None = None
    ) -> None:
        """Instantly create a PENDING record without touching the executor."""
        store.create(run_id)

    def test_submit_valid_returns_202(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("samba_service.app.submit_job", self._mock_submit)
        resp = client.post("/api/v1/jobs", json={"scenario": _MINIMAL_VALID})
        assert resp.status_code == 202

    def test_submit_returns_run_id(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("samba_service.app.submit_job", self._mock_submit)
        data = client.post("/api/v1/jobs", json={"scenario": _MINIMAL_VALID}).json()
        assert "run_id" in data
        assert isinstance(data["run_id"], str)
        assert len(data["run_id"]) > 0

    def test_submit_returns_poll_url(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("samba_service.app.submit_job", self._mock_submit)
        data = client.post("/api/v1/jobs", json={"scenario": _MINIMAL_VALID}).json()
        run_id = data["run_id"]
        assert data["poll_url"] == f"/api/v1/jobs/{run_id}"

    def test_submit_returns_pending_status(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("samba_service.app.submit_job", self._mock_submit)
        data = client.post("/api/v1/jobs", json={"scenario": _MINIMAL_VALID}).json()
        assert data["status"] == "pending"

    def test_submit_invalid_scenario_returns_422(self, client: TestClient) -> None:
        # Missing required fields → 422 without ever calling submit_job
        bad = {"schema_version": "1.0"}
        resp = client.post("/api/v1/jobs", json={"scenario": bad})
        assert resp.status_code == 422

    def test_submit_no_body_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/jobs", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestJobGet
# ---------------------------------------------------------------------------


class TestJobGet:
    """GET /api/v1/jobs/{run_id} — poll individual job."""

    def test_unknown_run_id_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/jobs/nonexistent-id-xyz")
        assert resp.status_code == 404

    def test_known_job_returns_200(self, client: TestClient, completed_job: Job) -> None:
        resp = client.get(f"/api/v1/jobs/{completed_job.run_id}")
        assert resp.status_code == 200

    def test_response_has_run_id(self, client: TestClient, completed_job: Job) -> None:
        data = client.get(f"/api/v1/jobs/{completed_job.run_id}").json()
        assert data["run_id"] == completed_job.run_id

    def test_response_has_status(self, client: TestClient, completed_job: Job) -> None:
        data = client.get(f"/api/v1/jobs/{completed_job.run_id}").json()
        assert data["status"] == "completed"

    def test_completed_job_has_kpis(self, client: TestClient, completed_job: Job) -> None:
        data = client.get(f"/api/v1/jobs/{completed_job.run_id}").json()
        assert data["kpis"] is not None
        assert isinstance(data["kpis"], dict)

    def test_completed_job_has_artifacts_list(self, client: TestClient, completed_job: Job) -> None:
        data = client.get(f"/api/v1/jobs/{completed_job.run_id}").json()
        assert "artifacts" in data
        assert isinstance(data["artifacts"], list)
        # The fixture wrote kpis.json and sizing.csv
        assert "kpis.json" in data["artifacts"]
        assert "sizing.csv" in data["artifacts"]


# ---------------------------------------------------------------------------
# TestJobList
# ---------------------------------------------------------------------------


class TestJobList:
    """GET /api/v1/jobs — list endpoint."""

    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/api/v1/jobs").status_code == 200

    def test_returns_list(self, client: TestClient) -> None:
        data = client.get("/api/v1/jobs").json()
        assert isinstance(data, list)

    def test_completed_job_appears_in_list(self, client: TestClient, completed_job: Job) -> None:
        ids = [j["run_id"] for j in client.get("/api/v1/jobs").json()]
        assert completed_job.run_id in ids

    def test_status_filter_completed(
        self, client: TestClient, completed_job: Job, pending_job: Job
    ) -> None:
        data = client.get("/api/v1/jobs?status=completed").json()
        statuses = {j["status"] for j in data}
        assert statuses == {"completed"} or len(data) == 0
        # completed_job should be present
        ids = [j["run_id"] for j in data]
        assert completed_job.run_id in ids
        # pending_job must NOT be present
        assert pending_job.run_id not in ids

    def test_status_filter_pending(
        self, client: TestClient, completed_job: Job, pending_job: Job
    ) -> None:
        data = client.get("/api/v1/jobs?status=pending").json()
        statuses = {j["status"] for j in data}
        assert statuses <= {"pending"}
        ids = [j["run_id"] for j in data]
        assert pending_job.run_id in ids
        assert completed_job.run_id not in ids

    def test_invalid_status_filter_returns_empty_or_400(self, client: TestClient) -> None:
        resp = client.get("/api/v1/jobs?status=bogus")
        # Either returns empty list (graceful ignore) or 400 / 422
        assert resp.status_code in {200, 400, 422}
        if resp.status_code == 200:
            assert resp.json() == []


# ---------------------------------------------------------------------------
# TestJobArtifacts
# ---------------------------------------------------------------------------


class TestJobArtifacts:
    """GET /api/v1/jobs/{run_id}/artifacts/{filename} — artifact download."""

    def test_download_kpis_json_returns_200(self, client: TestClient, completed_job: Job) -> None:
        resp = client.get(f"/api/v1/jobs/{completed_job.run_id}/artifacts/kpis.json")
        assert resp.status_code == 200

    def test_download_kpis_returns_valid_json(self, client: TestClient, completed_job: Job) -> None:
        resp = client.get(f"/api/v1/jobs/{completed_job.run_id}/artifacts/kpis.json")
        payload = resp.json()
        assert isinstance(payload, dict)
        assert "npc" in payload

    def test_disallowed_filename_returns_400(self, client: TestClient, completed_job: Job) -> None:
        resp = client.get(f"/api/v1/jobs/{completed_job.run_id}/artifacts/secrets.txt")
        assert resp.status_code == 400

    def test_path_traversal_returns_400(self, client: TestClient, completed_job: Job) -> None:
        # URL encoding of ../kpis.json — FastAPI routes through path param,
        # but we can try a double-encoded traversal; even without encoding it
        # should be caught by whitelist (the path segment won't be in _ALLOWED).
        resp = client.get(f"/api/v1/jobs/{completed_job.run_id}/artifacts/../kpis.json")
        # TestClient follows redirects; assert not a file delivery (should be 400 or 422)
        assert resp.status_code in {400, 404, 422}

    def test_pending_job_artifact_returns_409(self, client: TestClient, pending_job: Job) -> None:
        resp = client.get(f"/api/v1/jobs/{pending_job.run_id}/artifacts/kpis.json")
        assert resp.status_code == 409

    def test_unknown_job_artifact_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/jobs/no-such-job/artifacts/kpis.json")
        assert resp.status_code == 404

    def test_missing_file_on_disk_returns_404(self, client: TestClient, completed_job: Job) -> None:
        # sizing.csv exists on disk for completed_job, but dispatch.csv does
        # not — request that absent (but whitelisted) filename.
        resp = client.get(f"/api/v1/jobs/{completed_job.run_id}/artifacts/dispatch.csv")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestJobDelete
# ---------------------------------------------------------------------------


class TestJobDelete:
    """DELETE /api/v1/jobs/{run_id}."""

    def test_delete_returns_204(self, client: TestClient, tmp_path: Path) -> None:
        # Create a disposable job entry
        job = Job(
            run_id="delete-me-id",
            status=JobStatus.PENDING,
            submitted_at=datetime.now(UTC),
        )
        store._jobs["delete-me-id"] = job
        resp = client.delete("/api/v1/jobs/delete-me-id")
        assert resp.status_code == 204
        store._jobs.pop("delete-me-id", None)  # cleanup in case test failed

    def test_delete_removes_from_store(self, client: TestClient) -> None:
        job = Job(
            run_id="delete-check-id",
            status=JobStatus.PENDING,
            submitted_at=datetime.now(UTC),
        )
        store._jobs["delete-check-id"] = job
        client.delete("/api/v1/jobs/delete-check-id")
        # Subsequent GET should 404
        resp = client.get("/api/v1/jobs/delete-check-id")
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_404(self, client: TestClient) -> None:
        resp = client.delete("/api/v1/jobs/does-not-exist-xyz")
        assert resp.status_code == 404

    def test_delete_with_artifacts_flag_removes_dir(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "del_with_artifacts"
        run_dir.mkdir()
        (run_dir / "kpis.json").write_text("{}", encoding="utf-8")

        job = Job(
            run_id="delete-artifacts-id",
            status=JobStatus.COMPLETED,
            submitted_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            run_dir=run_dir,
        )
        store._jobs["delete-artifacts-id"] = job

        resp = client.delete("/api/v1/jobs/delete-artifacts-id?delete_artifacts=true")
        assert resp.status_code == 204
        # Artifact directory should be gone
        assert not run_dir.exists()


# ---------------------------------------------------------------------------
# Integration tests — real solver
# ---------------------------------------------------------------------------


@skip_no_solver
@pytest.mark.integration
@pytest.mark.slow
class TestJobFullLifecycle:
    """Full async job lifecycle using the real HiGHS solver.

    Uses the g01 golden scenario.  The test polls until COMPLETED (or FAILED)
    with a timeout of 10 minutes.
    """

    _POLL_INTERVAL = 2.0
    _TIMEOUT = 600.0  # seconds

    def _poll_until_done(self, client: TestClient, run_id: str) -> dict[str, Any]:
        """Block until job leaves PENDING/RUNNING or timeout."""
        deadline = time.monotonic() + self._TIMEOUT
        while time.monotonic() < deadline:
            resp = client.get(f"/api/v1/jobs/{run_id}")
            assert resp.status_code == 200
            data: dict[str, Any] = resp.json()
            if data["status"] in ("completed", "failed"):
                return data
            time.sleep(self._POLL_INTERVAL)
        pytest.fail(f"Job {run_id} did not complete within {self._TIMEOUT} s")

    def test_full_lifecycle_g01(
        self,
        g01_scenario_dict: dict[str, Any],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Submit, poll, and download results for the g01 golden scenario."""
        from samba_service.config import config as svc_config

        monkeypatch.setattr(svc_config, "data_dir", _G01_DIR)
        monkeypatch.setattr(svc_config, "run_base_dir", tmp_path)
        monkeypatch.setattr(svc_config, "max_concurrent", 1)

        with TestClient(app) as c:
            # 1. Submit
            resp = c.post("/api/v1/jobs", json={"scenario": g01_scenario_dict})
            assert resp.status_code == 202
            run_id = resp.json()["run_id"]

            # 2. Initial status is pending or running
            poll = c.get(f"/api/v1/jobs/{run_id}").json()
            assert poll["status"] in ("pending", "running", "completed")

            # 3. Poll until done
            final = self._poll_until_done(c, run_id)
            assert final["status"] == "completed", f"Job failed: {final.get('error')}"

            # 4. KPIs populated
            assert final["kpis"] is not None
            assert final["kpis"].get("lcoe", 0) > 0

            # 5. Artifact download — kpis.json
            assert "kpis.json" in final["artifacts"]
            art_resp = c.get(f"/api/v1/jobs/{run_id}/artifacts/kpis.json")
            assert art_resp.status_code == 200
            kpis_payload = art_resp.json()
            assert isinstance(kpis_payload, dict)

            # 6. Delete job
            del_resp = c.delete(f"/api/v1/jobs/{run_id}?delete_artifacts=false")
            assert del_resp.status_code == 204
            assert c.get(f"/api/v1/jobs/{run_id}").status_code == 404


@pytest.fixture(scope="module")
def g01_scenario_dict() -> dict[str, Any]:
    """Load the g01 golden scenario YAML as a plain dict."""
    import yaml

    with (_G01_DIR / "scenario.yaml").open(encoding="utf-8") as fh:
        return dict(yaml.safe_load(fh))
