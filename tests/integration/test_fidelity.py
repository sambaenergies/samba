# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Integration tests for v4 Phase 27 fidelity features through the full pipeline.

- Epsilon-constraint: a hard emissions cap reduces emissions and raises cost.
- Battery degradation: heavy cycling shortens the effective lifetime, adding
  replacements and raising NPC vs an undegraded battery.
"""

from __future__ import annotations

import importlib

import numpy as np
import pytest

pytestmark = pytest.mark.integration

_highs_available = importlib.util.find_spec("highspy") is not None
skip_no_solver = pytest.mark.skipif(not _highs_available, reason="highspy not installed")

_N = 8760


def _run(*, max_emissions=None, degradation=None, battery=True):
    from samba.compiler import CompilerInputs, compile_energy_system
    from samba.run_result.kpis import compute_kpis
    from samba.scenario.models import Scenario
    from samba.solver import SolverConfig, extract_dispatch, solve
    from samba.tariff import resolve_tariff
    from samba.weather import stub_weather

    components: dict = {
        "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
        "grid": {"capacity_kw": 100.0, "emission_factor_kg_per_kwh": 0.4},
        "pv": {"capacity_kw": None, "capex_per_kw": 1000.0},
    }
    if battery:
        batt: dict = {
            "capacity_kwh": 30.0,
            "power_kw": 15.0,
            "capex_per_kwh": 300.0,
            "lifetime_years": 15,
        }
        if degradation is not None:
            batt["degradation"] = degradation
        components["battery"] = batt

    scenario = Scenario.model_validate(
        {
            "project": {"name": "fidelity-it", "discount_rate_nominal": 0.08, "lifetime_years": 25},
            "location": {
                "latitude": 37.77,
                "longitude": -122.42,
                "timezone": "America/Los_Angeles",
            },
            "weather": {"source": "csv", "csv_path": "d.csv"},
            "load": {"source": "hourly_csv", "csv_path": "d.csv"},
            "components": components,
            "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.15}},
            "constraints": ({"max_total_emissions_kg": max_emissions} if max_emissions else {}),
        }
    )
    load = np.full(_N, 6.0, dtype=np.float64)
    day = np.concatenate([np.zeros(6), np.linspace(0, 1, 6), np.linspace(1, 0, 6), np.zeros(6)])
    pv_per_kwp = np.tile(day, 365)[:_N]
    ta = resolve_tariff(scenario.tariff, load, year=2025)
    inputs = CompilerInputs(
        scenario=scenario,
        load_kw=load,
        tariff_arrays=ta,
        weather=stub_weather(),
        pv_per_kwp=pv_per_kwp,
    )
    es = compile_energy_system(inputs)
    res = solve(es, scenario, config=SolverConfig(solver_name="appsi_highs"))
    dr = extract_dispatch(es, res)
    kpis, econ, _ = compute_kpis(scenario, dr, ta)
    return kpis, econ


@skip_no_solver
class TestEpsilonConstraint:
    def test_cap_reduces_emissions_and_raises_cost(self) -> None:
        base_k, _ = _run(battery=False)
        cap = base_k["total_emissions_kg"] * 0.9
        capped_k, _ = _run(max_emissions=cap, battery=False)
        assert capped_k["total_emissions_kg"] <= cap + 1.0  # cap enforced
        assert capped_k["npc"] > base_k["npc"]  # cleaner is costlier here


@skip_no_solver
class TestBatteryDegradation:
    def test_heavy_cycling_shortens_life_and_raises_npc(self) -> None:
        # Nameplate 15 yr; aggressive cycle fade so cycling drives EOL well below it.
        deg = {
            "calendar_fade_pct_yr": 1.0,
            "cycle_fade_pct_per_efc": 0.05,
            "end_of_life_capacity_pct": 80.0,
        }
        base_k, base_e = _run()  # no degradation -> nameplate 15 yr
        deg_k, deg_e = _run(degradation=deg)

        assert base_k["battery_eol_year"] == 15  # nameplate when no degradation
        assert deg_k["battery_eol_year"] < 15  # cycling shortens life
        assert deg_k["annual_throughput_cycles"] > 0.0
        # Shorter battery life -> more replacements over the 25-yr project.
        base_repl = base_e["replacement_schedule"].get("battery", {}).get("replacements", 0)
        deg_repl = deg_e["replacement_schedule"].get("battery", {}).get("replacements", 0)
        assert deg_repl > base_repl
        assert deg_k["npc"] > base_k["npc"]
