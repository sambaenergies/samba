# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Integration tests for KiBaM battery chemistry.

Compiles and solves real LP problems using HiGHS.  Skipped if highspy is not
installed.

Scenarios exercised:

1. **KiBaM basic** — PV + KiBaM battery + grid, flat rate.  Verify solve
   completes, SOC stays within bounds, and dispatch columns are present.
2. **KiBaM vs Li-ion** — same scenario with chemistry="li_ion"; confirm
   KiBaM NPC ≥ Li-ion NPC (KiBaM is more constrained so at least as expensive).
3. **Post-validation** — unit-level; inject aggressive dispatch into
   validate_kibam_dispatch and confirm infeasibility is detected.
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
_LOAD_KW = np.full(_N, 2.0, dtype=np.float64)  # 2 kW flat load
# Simple daytime PV profile: 0.5 kW/kWp for 12 hours, zero at night
_PV_HALF = np.where(
    np.tile(np.concatenate([np.ones(12) * 0.5, np.zeros(12)]), 365),
    0.5,
    0.0,
).astype(np.float64)

try:
    from samba.tariff import TariffArrays

    _TARIFF = TariffArrays(
        cbuy=np.full(_N, 0.20, dtype=np.float64),
        csell=np.zeros(_N, dtype=np.float64),
        service_charge=np.zeros(12),
    )
except Exception:  # pragma: no cover
    _TARIFF = None  # type: ignore[assignment]


def _make_scenario(**overrides: Any) -> Any:
    """Build a minimal Scenario with optional overrides."""
    from samba.scenario.models import Scenario

    def _deep_update(base: dict, updates: dict) -> None:  # type: ignore[type-arg]
        for k, v in updates.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                _deep_update(base[k], v)
            else:
                base[k] = v

    base: dict[str, Any] = {
        "project": {"name": "kibam-integ-test", "discount_rate_nominal": 0.08, "year": 2023},
        "location": {
            "latitude": 37.77,
            "longitude": -122.42,
            "timezone": "America/Los_Angeles",
        },
        "weather": {"source": "csv", "csv_path": "dummy.csv"},
        "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
        "components": {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
            "pv": {"capex_per_kw": 1000.0, "capacity_kw": 5.0},
            "grid": {"capacity_kw": 20.0},
        },
        "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.20}},
    }
    _deep_update(base, overrides)
    return Scenario.model_validate(base)


def _compile_and_solve(scenario: Any) -> Any:
    from samba.compiler import CompilerInputs, compile_energy_system
    from samba.solver import SolverConfig, extract_dispatch, solve
    from samba.weather import stub_weather as _stub_weather

    inputs = CompilerInputs(
        scenario=scenario,
        load_kw=_LOAD_KW.copy(),
        tariff_arrays=_TARIFF,
        weather=_stub_weather(),
        pv_per_kwp=_PV_HALF.copy(),
    )
    es = compile_energy_system(inputs)
    config = SolverConfig(solver_name="appsi_highs", kibam_validate=False)  # skip post-val here
    raw = solve(es, scenario, config=config)
    return extract_dispatch(es, raw)


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestKiBaMBasic:
    @skip_no_solver
    def test_kibam_solve_completes(self) -> None:
        """KiBaM + PV + grid scenario should solve without error."""
        scenario = _make_scenario(
            components={
                "battery": {
                    "capex_per_kwh": 250.0,
                    "capacity_kwh": 10.0,
                    "chemistry": "kibam",
                    "c_rate_charge": 1.0,
                    "c_rate_discharge": 1.0,
                }
            }
        )
        dr = _compile_and_solve(scenario)
        assert dr is not None

    @skip_no_solver
    def test_kibam_battery_columns_present(self) -> None:
        """Dispatch must contain batt_charge, batt_discharge, battery_soc_kwh."""
        scenario = _make_scenario(
            components={
                "battery": {
                    "capex_per_kwh": 250.0,
                    "capacity_kwh": 10.0,
                    "chemistry": "kibam",
                }
            }
        )
        dr = _compile_and_solve(scenario)
        for col in ("batt_charge", "batt_discharge", "battery_soc_kwh"):
            assert col in dr.dispatch.columns, f"Missing column: {col}"

    @skip_no_solver
    def test_kibam_soc_within_bounds(self) -> None:
        """SOC must stay within [soc_min * capacity, soc_max * capacity]."""
        cap = 10.0
        soc_min = 0.2
        soc_max = 1.0
        scenario = _make_scenario(
            components={
                "battery": {
                    "capex_per_kwh": 250.0,
                    "capacity_kwh": cap,
                    "chemistry": "kibam",
                    "soc_min": soc_min,
                    "soc_max": soc_max,
                }
            }
        )
        dr = _compile_and_solve(scenario)
        soc_kwh = dr.dispatch["battery_soc_kwh"].to_numpy()
        assert (soc_kwh >= soc_min * cap - 1e-4).all(), "SOC went below soc_min"
        assert (soc_kwh <= soc_max * cap + 1e-4).all(), "SOC exceeded soc_max"

    @skip_no_solver
    def test_kibam_non_negative_dispatch(self) -> None:
        """Charge and discharge columns must be non-negative."""
        scenario = _make_scenario(
            components={
                "battery": {
                    "capex_per_kwh": 250.0,
                    "capacity_kwh": 10.0,
                    "chemistry": "kibam",
                }
            }
        )
        dr = _compile_and_solve(scenario)
        assert (dr.dispatch["batt_charge"] >= -1e-6).all()
        assert (dr.dispatch["batt_discharge"] >= -1e-6).all()


class TestKiBaMVsLiIon:
    @skip_no_solver
    def test_kibam_npc_ge_li_ion(self) -> None:
        """KiBaM (more constrained) NPC should be ≥ Li-ion NPC for same scenario."""
        from samba.run_result.kpis import compute_kpis

        base_components = {
            "battery": {
                "capex_per_kwh": 250.0,
                "capacity_kwh": 10.0,
                "c_rate_charge": 1.0,
                "c_rate_discharge": 1.0,
            }
        }

        sc_li = _make_scenario(components={**base_components})  # default li_ion
        sc_ki = _make_scenario(
            components={"battery": {**base_components["battery"], "chemistry": "kibam"}}
        )

        dr_li = _compile_and_solve(sc_li)
        dr_ki = _compile_and_solve(sc_ki)

        kpis_li, _, _ = compute_kpis(sc_li, dr_li, _TARIFF)
        kpis_ki, _, _ = compute_kpis(sc_ki, dr_ki, _TARIFF)

        # KiBaM has tighter C-rate constraints → same or higher total cost
        # Allow a small tolerance because the LP may find equivalent solutions
        assert kpis_ki["npc"] >= kpis_li["npc"] - 1.0, (
            f"KiBaM NPC ({kpis_ki['npc']:.2f}) should be >= Li-ion NPC ({kpis_li['npc']:.2f})"
        )


class TestKiBaMPostValidation:
    def test_aggressive_dispatch_infeasible(self) -> None:
        """validate_kibam_dispatch detects infeasibility for aggressive dispatch."""
        from samba.batteries.kibam import validate_kibam_dispatch
        from samba.scenario.models import KiBaMParams

        cap = 10.0
        # Discharge at 1C for 40 hours from low SOC → Q1 should go negative
        dispatch = np.concatenate([np.full(40, cap), np.zeros(8720)])
        result = validate_kibam_dispatch(
            dispatch_kw=dispatch,
            capacity_kwh=cap,
            kibam=KiBaMParams(),
            soc_initial=0.25,
        )
        assert result.feasible is False
        assert result.n_violations > 0

    def test_gentle_dispatch_feasible(self) -> None:
        """validate_kibam_dispatch returns feasible for conservative dispatch."""
        from samba.batteries.kibam import validate_kibam_dispatch
        from samba.scenario.models import KiBaMParams

        cap = 10.0
        # Very gentle 0.02C discharge
        dispatch = np.full(8760, 0.02 * cap / 8760, dtype=np.float64)
        result = validate_kibam_dispatch(
            dispatch_kw=dispatch,
            capacity_kwh=cap,
            kibam=KiBaMParams(),
            soc_initial=0.8,
        )
        assert result.feasible is True
