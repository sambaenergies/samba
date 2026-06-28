# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Capture golden KPIs for all 6 v2 golden scenarios and print JSON."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

# Suppress Pyomo NonConvexFlowBlock replacement warning
warnings.filterwarnings("ignore", category=UserWarning, module="pyomo")
import samba  # noqa: E402
from samba.input_resolver import resolve_arrays  # noqa: E402
from samba.scenario import load_scenario  # noqa: E402

GOLDENS = Path(__file__).parent.parent / "tests" / "goldens"
DIRS = [
    "g07_multi_objective",
    "g08_dg_unit_commitment",
    "g09_ev_smart_charge",
    "g10_ev_v2g",
    "g11_kibam_battery",
    "g12_tiered_tariff_endogenous",
]


def run_one(d: str) -> dict[str, Any]:
    sd = GOLDENS / d
    scenario = load_scenario(sd / "scenario.yaml")
    load_kw, pv_per_kwp, wind_kw = resolve_arrays(scenario, sd)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_kw,
        output_dir=None,
    )
    kpis = result.kpis
    sizing = result.sizing

    def _sz(c: str) -> float:
        if sizing is None or sizing.empty:
            return 0.0
        r = sizing[sizing["component"] == c]
        return float(r["capacity"].sum()) if not r.empty else 0.0

    return {
        "npc": round(kpis.get("npc", 0.0), 2),
        "lcoe": round(kpis.get("lcoe", 0.0), 6),
        "pv_kw": round(_sz("pv"), 4),
        "battery_kwh": round(_sz("battery_energy"), 4),
        "inverter_kw": round(_sz("inverter"), 4),
        "annual_pv_kwh": round(kpis.get("total_pv_generation", 0.0), 2),
        "renewable_fraction": round(kpis.get("renewable_fraction", 0.0), 6),
        "annual_diesel_l": round(kpis.get("dg_fuel_consumption_liters", 0.0), 2),
        "total_emissions_kg": round(kpis.get("total_emissions_kg", 0.0), 2),
        "total_grid_bought": round(kpis.get("total_grid_bought", 0.0), 2),
        "annual_ev_charge_kwh": round(kpis.get("annual_ev_charge_kwh", 0.0), 2),
        "annual_ev_discharge_kwh": round(kpis.get("annual_ev_discharge_kwh", 0.0), 2),
        "ev_v2g_revenue": round(kpis.get("ev_v2g_revenue", 0.0), 2),
        "lpsp": round(kpis.get("lpsp", 0.0), 6),
        "dg_operating_hours": kpis.get("dg_operating_hours", 0),
        "total_grid_cost_net": round(kpis.get("total_grid_cost_net", 0.0), 2),
        "monthly_grid_kwh": [round(v, 2) for v in kpis.get("monthly_grid_kwh", [])],
    }


if __name__ == "__main__":
    import traceback

    results: dict[str, dict[str, Any] | str] = {}
    for d in DIRS:
        print(f"Running {d} ...", flush=True)
        try:
            res = run_one(d)
            results[d] = res
            print(f"  OK  npc={res['npc']}")
        except Exception:
            results[d] = "ERROR"
            traceback.print_exc()

    print("\n\n=== RESULTS JSON ===")
    print(json.dumps(results, indent=2))
