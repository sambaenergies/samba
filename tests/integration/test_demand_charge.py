# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Integration tests for the v4 demand charge through the full compiler pipeline.

Confirms the LP peak-shaving incentive (audit/v4 Phase 25): adding a
``$/kW-month`` demand charge to a scenario with storage reduces the monthly peak
grid import and raises NPC, and the economics layer reports the charge.
"""

from __future__ import annotations

import importlib

import numpy as np
import pytest

pytestmark = pytest.mark.integration

_highs_available = importlib.util.find_spec("highspy") is not None
skip_no_solver = pytest.mark.skipif(not _highs_available, reason="highspy not installed")

_N = 8760


def _solve_with_demand(rate_per_kw_month: float) -> tuple[float, float, dict]:
    """Return (npc, monthly_peak_max_kw, grid_breakdown) for a PV+battery+grid run."""
    from samba.compiler import CompilerInputs, compile_energy_system
    from samba.economics.cashflow import build_economics
    from samba.scenario.models import Scenario
    from samba.solver import SolverConfig, extract_dispatch, solve
    from samba.tariff import resolve_tariff
    from samba.tariff.demand import monthly_peak_import
    from samba.weather import stub_weather

    tariff: dict = {
        "buy": {"type": "flat", "rate_per_kwh": 0.20},
        "sell": {"type": "flat", "rate_per_kwh": 0.05},
    }
    if rate_per_kw_month > 0.0:
        tariff["demand_charge"] = {"rate_per_kw_month": rate_per_kw_month}

    scenario = Scenario.model_validate(
        {
            "project": {"name": "demand-charge-it", "discount_rate_nominal": 0.08},
            "location": {
                "latitude": 37.77,
                "longitude": -122.42,
                "timezone": "America/Los_Angeles",
            },
            "weather": {"source": "csv", "csv_path": "d.csv"},
            "load": {"source": "hourly_csv", "csv_path": "d.csv"},
            "components": {
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                "grid": {"capacity_kw": 100.0, "export_allowed": True, "export_capacity_kw": 50.0},
                "pv": {"capacity_kw": 15.0, "capex_per_kw": 1000.0},
                "battery": {"capacity_kwh": 60.0, "power_kw": 30.0, "capex_per_kwh": 300.0},
            },
            "tariff": tariff,
        }
    )

    # Flat 5 kW base load with a sharp 30 kW evening spike every day -> a peak to shave.
    load = np.full(_N, 5.0, dtype=np.float64)
    load[np.arange(_N) % 24 == 19] = 30.0
    # Simple midday PV bell so storage has something to time-shift.
    day = np.concatenate([np.zeros(6), np.linspace(0, 1, 6), np.linspace(1, 0, 6), np.zeros(6)])
    pv_per_kwp = np.tile(day, 365)[:_N]

    tariff_arrays = resolve_tariff(scenario.tariff, load, year=2025)
    inputs = CompilerInputs(
        scenario=scenario,
        load_kw=load,
        tariff_arrays=tariff_arrays,
        weather=stub_weather(),
        pv_per_kwp=pv_per_kwp,
    )
    es = compile_energy_system(inputs)
    results = solve(es, scenario, config=SolverConfig(solver_name="appsi_highs"))
    dr = extract_dispatch(es, results)
    econ = build_economics(scenario, dr, tariff_arrays)
    peak_max = float(monthly_peak_import(dr.dispatch["grid_buy"].to_numpy()).max())
    return econ["npc"], peak_max, econ["grid"]


@skip_no_solver
class TestDemandChargePeakShaving:
    def test_demand_charge_shaves_peak_and_raises_npc(self) -> None:
        npc0, peak0, grid0 = _solve_with_demand(0.0)
        npc1, peak1, grid1 = _solve_with_demand(50.0)

        # Peak shaving: the priced peak is materially lower than the unpriced one.
        assert peak1 < peak0 - 1.0, f"expected peak shaving: {peak1:.2f} vs {peak0:.2f}"
        # The charge is a real added cost.
        assert npc1 > npc0
        # Economics reports a positive demand charge when priced, zero when not.
        assert grid0["annual_demand_charge_yr1"] == 0.0
        assert grid1["annual_demand_charge_yr1"] > 0.0

    def test_no_demand_charge_is_unchanged_path(self) -> None:
        # A zero-rate run must not add the demand term.
        _, _, grid = _solve_with_demand(0.0)
        assert grid["annual_demand_charge_yr1"] == 0.0
        assert grid["total_demand_charge_npv"] == 0.0
