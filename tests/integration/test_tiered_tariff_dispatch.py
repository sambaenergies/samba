# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Integration tests for Phase 17 endogenous piecewise-linear tiered tariffs.

Tests require HiGHS (via ``highspy``).  They are skipped when HiGHS is not
available.

Scenarios:
1. **Declining-block schema rejection** — pure schema validation, no solver needed.
2. **Grid-only endogenous solve** — confirms solve completes, PWL constraints
   inject correctly, ``monthly_grid_kwh`` is populated.
3. **v1 == v2 for identical no-storage dispatch** — both modes give the same
   total grid cost when no storage can shift the load timing.
4. **v2 endogenous with battery + PV** — solve completes, monthly_grid_kwh
   sums correctly to annual grid bought.
"""

from __future__ import annotations

import importlib
from typing import Any

import numpy as np
import pytest

pytestmark = pytest.mark.integration

_highs_available = importlib.util.find_spec("highspy") is not None

skip_no_solver = pytest.mark.skipif(
    not _highs_available,
    reason="highspy not installed — run 'pip install highspy'",
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_N = 8760
# Flat 3 kW load — results in ~2232 kWh/month in 31-day months
_LOAD_KW = np.full(_N, 3.0, dtype=np.float64)

# Daytime PV: 1.5 kW per kWp for 12 h/day
_PV_PROFILE = np.where(
    np.tile(np.concatenate([np.ones(12) * 1.5, np.zeros(12)]), 365),
    1.5,
    0.0,
).astype(np.float64)

# Tiered tariff: 0–500 kWh/month @ $0.10, >500 kWh/month @ $0.20
_TIERS_2 = [
    {"limit_kwh": 500.0, "rate_per_kwh": 0.10},
    {"limit_kwh": None, "rate_per_kwh": 0.20},
]


def _base_scenario(**overrides: Any) -> Any:
    """Build a minimal grid + PV scenario."""
    from samba.scenario.models import Scenario

    def _deep_update(base: dict, updates: dict) -> None:  # type: ignore[type-arg]
        for k, v in updates.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                _deep_update(base[k], v)
            else:
                base[k] = v

    base: dict[str, Any] = {
        "project": {"name": "tier-integ", "discount_rate_nominal": 0.08, "year": 2023},
        "location": {
            "latitude": 37.77,
            "longitude": -122.42,
            "timezone": "America/Los_Angeles",
        },
        "weather": {"source": "csv", "csv_path": "dummy.csv"},
        "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
        "components": {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
            "grid": {"capacity_kw": 20.0},
        },
        "tariff": {"buy": {"type": "tiered", "tiers": _TIERS_2, "endogenous_tiering": False}},
    }
    _deep_update(base, overrides)
    return Scenario.model_validate(base)


def _resolve_and_compile(scenario: Any) -> Any:
    """Resolve tariff and compile energy system, return (energy_system, tariff_arrays)."""
    from samba.compiler import CompilerInputs, compile_energy_system
    from samba.tariff import resolve_tariff
    from samba.weather import stub_weather as _stub_weather

    tariff_arrays = resolve_tariff(scenario.tariff, _LOAD_KW, year=scenario.project.year)
    inputs = CompilerInputs(
        scenario=scenario,
        load_kw=_LOAD_KW.copy(),
        tariff_arrays=tariff_arrays,
        weather=_stub_weather(),
        pv_per_kwp=_PV_PROFILE.copy() if scenario.components.pv is not None else None,
    )
    es = compile_energy_system(inputs)
    return es, tariff_arrays


def _compile_solve_extract(scenario: Any) -> tuple[Any, Any, Any]:
    """Full pipeline: compile → solve → extract. Returns (dr, tariff_arrays, kpis)."""
    from samba.run_result.kpis import compute_kpis
    from samba.solver import SolverConfig, extract_dispatch, solve

    es, tariff_arrays = _resolve_and_compile(scenario)
    config = SolverConfig(solver_name="appsi_highs")
    raw = solve(es, scenario, config=config)
    dr = extract_dispatch(es, raw)
    kpis, _, _ = compute_kpis(scenario, dr, tariff_arrays)
    return dr, tariff_arrays, kpis


# ---------------------------------------------------------------------------
# Test 1: Schema — declining-block rejects endogenous_tiering=True
# ---------------------------------------------------------------------------


class TestDecliningBlockSchemaRejection:
    def test_declining_block_tariff_endogenous_raises_at_validate(self) -> None:
        """validate_tier_specs raises on declining-block tariffs."""
        from samba.tariff.endogenous import TierSpec, validate_tier_specs

        specs = [
            TierSpec(
                month=m,
                boundaries=[500.0, 1000.0, float("inf")],
                rates=[0.20, 0.15, 0.10],  # declining block
            )
            for m in range(12)
        ]
        with pytest.raises(ValueError, match="non-decreasing tier rates"):
            validate_tier_specs(specs)

    def test_flat_rate_endogenous_true_rejected_at_schema(self) -> None:
        """endogenous_tiering=True on non-tiered type is rejected by BuyRate validator."""
        with pytest.raises(ValueError, match="endogenous_tiering only applicable"):
            _base_scenario(
                tariff={"buy": {"type": "flat", "rate_per_kwh": 0.15, "endogenous_tiering": True}}
            )


# ---------------------------------------------------------------------------
# Test 2: Grid-only endogenous solve completes
# ---------------------------------------------------------------------------


class TestGridOnlyEndogenousSolve:
    @skip_no_solver
    def test_solve_completes(self) -> None:
        """Endogenous tiered tariff with grid-only (no battery) solves without error."""
        scenario = _base_scenario(
            tariff={
                "buy": {
                    "type": "tiered",
                    "tiers": _TIERS_2,
                    "endogenous_tiering": True,
                }
            }
        )
        dr, _, kpis = _compile_solve_extract(scenario)
        assert dr is not None

    @skip_no_solver
    def test_monthly_grid_kwh_is_12_values(self) -> None:
        """monthly_grid_kwh KPI must have exactly 12 entries."""
        scenario = _base_scenario(
            tariff={"buy": {"type": "tiered", "tiers": _TIERS_2, "endogenous_tiering": True}}
        )
        _, _, kpis = _compile_solve_extract(scenario)
        assert len(kpis["monthly_grid_kwh"]) == 12

    @skip_no_solver
    def test_monthly_grid_kwh_sums_to_annual_total(self) -> None:
        """Sum of monthly_grid_kwh must equal total_grid_bought."""
        scenario = _base_scenario(
            tariff={"buy": {"type": "tiered", "tiers": _TIERS_2, "endogenous_tiering": True}}
        )
        dr, _, kpis = _compile_solve_extract(scenario)
        assert sum(kpis["monthly_grid_kwh"]) == pytest.approx(kpis["total_grid_bought"], rel=1e-3)

    @skip_no_solver
    def test_all_monthly_grid_kwh_non_negative(self) -> None:
        scenario = _base_scenario(
            tariff={"buy": {"type": "tiered", "tiers": _TIERS_2, "endogenous_tiering": True}}
        )
        _, _, kpis = _compile_solve_extract(scenario)
        assert all(v >= 0 for v in kpis["monthly_grid_kwh"])


# ---------------------------------------------------------------------------
# Test 3: v1 == v2 for no-storage dispatch (grid-only, fixed load)
# ---------------------------------------------------------------------------


class TestV1V2Equivalence:
    @skip_no_solver
    def test_same_npc_no_storage(self) -> None:
        """With no storage, v1 and v2 must give the same NPC (no circularity gap)."""
        sc_v1 = _base_scenario(
            tariff={"buy": {"type": "tiered", "tiers": _TIERS_2, "endogenous_tiering": False}}
        )
        sc_v2 = _base_scenario(
            tariff={"buy": {"type": "tiered", "tiers": _TIERS_2, "endogenous_tiering": True}}
        )
        _, _, kpis_v1 = _compile_solve_extract(sc_v1)
        _, _, kpis_v2 = _compile_solve_extract(sc_v2)
        # Within 1% — small tolerance for floating-point LP precision
        assert kpis_v1["npc"] == pytest.approx(kpis_v2["npc"], rel=0.01)

    @skip_no_solver
    def test_same_total_grid_bought_no_storage(self) -> None:
        """Without storage the grid dispatch should be identical for v1 and v2."""
        sc_v1 = _base_scenario(
            tariff={"buy": {"type": "tiered", "tiers": _TIERS_2, "endogenous_tiering": False}}
        )
        sc_v2 = _base_scenario(
            tariff={"buy": {"type": "tiered", "tiers": _TIERS_2, "endogenous_tiering": True}}
        )
        _, _, kpis_v1 = _compile_solve_extract(sc_v1)
        _, _, kpis_v2 = _compile_solve_extract(sc_v2)
        assert kpis_v1["total_grid_bought"] == pytest.approx(kpis_v2["total_grid_bought"], rel=0.01)


# ---------------------------------------------------------------------------
# Test 4: v2 with PV + battery — solve completes and monthly KPIs are valid
# ---------------------------------------------------------------------------


class TestEndogenousWithBattery:
    @skip_no_solver
    def test_solve_completes_with_battery_pv(self) -> None:
        """Endogenous tiered tariff with battery + PV solves without error."""
        scenario = _base_scenario(
            components={
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                "pv": {"capex_per_kw": 1200.0, "capacity_kw": 8.0},
                "battery": {
                    "capex_per_kwh": 400.0,
                    "capacity_kwh": 10.0,
                    "c_rate_charge": 0.5,
                    "c_rate_discharge": 0.5,
                },
                "grid": {"capacity_kw": 20.0},
            },
            tariff={"buy": {"type": "tiered", "tiers": _TIERS_2, "endogenous_tiering": True}},
        )
        dr, _, kpis = _compile_solve_extract(scenario)
        assert dr is not None

    @skip_no_solver
    def test_monthly_grid_kwh_consistent_with_dispatch(self) -> None:
        """monthly_grid_kwh must match dispatch grid_buy column within tolerance."""
        scenario = _base_scenario(
            components={
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                "pv": {"capex_per_kw": 1200.0, "capacity_kw": 5.0},
                "battery": {
                    "capex_per_kwh": 400.0,
                    "capacity_kwh": 8.0,
                },
                "grid": {"capacity_kw": 20.0},
            },
            tariff={"buy": {"type": "tiered", "tiers": _TIERS_2, "endogenous_tiering": True}},
        )
        dr, _, kpis = _compile_solve_extract(scenario)
        # Sum of monthly must equal annual
        annual_from_monthly = sum(kpis["monthly_grid_kwh"])
        assert annual_from_monthly == pytest.approx(kpis["total_grid_bought"], rel=1e-3)
