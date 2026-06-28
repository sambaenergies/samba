"""Tests for the SAMBA REST service.

Fast tests (no solver, <1 s each):
  test_health, test_docs, test_openapi, test_validate_* , test_run_invalid_schema_*

Integration tests (real solver, ~5-15 min, marked ``slow`` + ``integration``):
  test_run_valid_scenario, test_run_infeasible_scenario

Run only fast tests:
    pytest tests/unit/test_service.py -m "not slow"

Run all service tests (including solver):
    pytest tests/unit/test_service.py -v
"""

from __future__ import annotations

import importlib.util
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from samba_service.app import app

# ---------------------------------------------------------------------------
# Solver availability guard
# ---------------------------------------------------------------------------

_highs_available = importlib.util.find_spec("highspy") is not None
skip_no_solver = pytest.mark.skipif(
    not _highs_available,
    reason="highspy not installed — run 'pip install highspy' or 'pip install -e .'",
)

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

#: Absolute path to the g01 golden scenario directory.
_G01_DIR = Path(__file__).parent.parent / "goldens" / "g01_grid_pv_batt"

#: Minimal *valid* scenario dict (all required fields; no CSV needed for validation).
_MINIMAL_VALID: dict[str, Any] = {
    "schema_version": "1.0",
    "project": {
        "name": "svc-validate-test",
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
        "csv_path": "dummy.csv",  # existence not checked during validation
    },
    "load": {"source": "generic_annual_total", "annual_kwh": 17520.0},
    "components": {
        "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
        "grid": {"capacity_kw": 100.0},
    },
    "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.15}},
}

#: Infeasible scenario: diesel generator (1 kW) < flat load (5 kW), no grid.
#: ``force_grid_disconnect=True`` and ``max_lpsp=0.0`` guarantee the LP is
#: infeasible regardless of dispatch decisions.  No weather/PV → no CSV needed.
_INFEASIBLE: dict[str, Any] = {
    "schema_version": "1.0",
    "project": {
        "name": "svc-infeasible-test",
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
        "csv_path": "dummy.csv",  # not loaded — no PV/wind component
    },
    "load": {"source": "generic_annual_total", "annual_kwh": 43800.0},
    "components": {
        "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
        "diesel_generator": {
            "capacity_kw": 1.0,  # 1 kW < 5 kW load at every hour → infeasible
            "capex_per_kw": 500.0,
            "fuel_price_per_l": 1.5,
        },
    },
    "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.15}},
    "constraints": {"force_grid_disconnect": True, "max_lpsp": 0.0},
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Shared FastAPI TestClient — runs lifespan (executor starts/stops)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def g01_scenario_dict() -> dict[str, Any]:
    """Load the g01 golden scenario YAML as a plain dict."""
    with (_G01_DIR / "scenario.yaml").open(encoding="utf-8") as fh:
        return dict(yaml.safe_load(fh))


# ---------------------------------------------------------------------------
# Fast tests — no solver required
# ---------------------------------------------------------------------------


class TestHealth:
    def test_status_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_version_present(self, client: TestClient) -> None:
        resp = client.get("/health")
        data = resp.json()
        assert "version" in data
        from samba._version import __version__

        assert data["version"] == __version__

    def test_solver_field_present(self, client: TestClient) -> None:
        resp = client.get("/health")
        data = resp.json()
        assert "solver" in data
        assert "solver_ready" in data
        assert isinstance(data["solver_ready"], bool)


class TestDocs:
    def test_swagger_ui_loads(self, client: TestClient) -> None:
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_openapi_schema(self, client: TestClient) -> None:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema
        assert "info" in schema

    def test_openapi_has_key_paths(self, client: TestClient) -> None:
        resp = client.get("/openapi.json")
        paths = resp.json()["paths"]
        assert "/health" in paths
        assert "/api/v1/validate" in paths
        assert "/api/v1/jobs" in paths


class TestValidate:
    def test_valid_scenario_returns_true(self, client: TestClient) -> None:
        resp = client.post("/api/v1/validate", json={"scenario": _MINIMAL_VALID})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_missing_project_returns_false(self, client: TestClient) -> None:
        bad = {
            "schema_version": "1.0"
        }  # missing project, location, weather, load, components, tariff
        resp = client.post("/api/v1/validate", json={"scenario": bad})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_invalid_latitude_returns_false(self, client: TestClient) -> None:
        bad = {
            **_MINIMAL_VALID,
            "location": {"latitude": 999.0, "longitude": 0.0, "timezone": "UTC"},
        }
        resp = client.post("/api/v1/validate", json={"scenario": bad})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert any("latitude" in e for e in data["errors"])

    def test_extra_field_forbidden(self, client: TestClient) -> None:
        """Extra top-level fields are rejected because Scenario uses extra='forbid'."""
        bad = {**_MINIMAL_VALID, "unknown_top_level_key": 42}
        resp = client.post("/api/v1/validate", json={"scenario": bad})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False


class TestJobSchemaValidation:
    """Fast tests that exercise the 422 path on POST /api/v1/jobs."""

    def test_missing_required_fields_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/jobs", json={"scenario": {"schema_version": "1.0"}})
        assert resp.status_code == 422

    def test_invalid_latitude_returns_422(self, client: TestClient) -> None:
        bad = {
            **_MINIMAL_VALID,
            "location": {"latitude": 200.0, "longitude": 0.0, "timezone": "UTC"},
        }
        resp = client.post("/api/v1/jobs", json={"scenario": bad})
        assert resp.status_code == 422
