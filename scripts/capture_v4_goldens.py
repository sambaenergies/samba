# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Capture reference.json for the v4 golden scenarios (g20-g22).

Runs each scenario once and writes a complete reference.json (required KPI keys +
v4 KPIs + tolerances + series_kpis) next to the scenario.yaml.

    python scripts/capture_v4_goldens.py
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", category=UserWarning, module="pyomo")

import samba  # noqa: E402
from samba.input_resolver import resolve_arrays  # noqa: E402
from samba.scenario import load_scenario  # noqa: E402

GOLDENS = Path(__file__).parent.parent / "tests" / "goldens"
DIRS = ["g20_demand_charge", "g21_nem_net_billing", "g22_bifacial_pv"]

# Relative tolerance for monetary / energy KPIs; absolute for near-zero values.
_REL = {"type": "relative", "value": 0.02}
_ABS = {"type": "absolute", "value": 0.5}


def _sz(sizing: Any, comp: str) -> float:
    if sizing is None or sizing.empty:
        return 0.0
    r = sizing[sizing["component"] == comp]
    return float(r["capacity"].sum()) if not r.empty else 0.0


def capture(name: str) -> None:
    sd = GOLDENS / name
    scenario = load_scenario(sd / "scenario.yaml")
    load_kw, pv_per_kwp, wind_kw = resolve_arrays(scenario, sd)
    result = samba.run(
        scenario, load_kw=load_kw, pv_per_kwp=pv_per_kwp, wind_power_kw=wind_kw, output_dir=None
    )
    k = result.kpis
    kpis: dict[str, float] = {
        "npc": round(k.get("npc", 0.0), 2),
        "lcoe": round(k.get("lcoe", 0.0), 6),
        "pv_kw": round(_sz(result.sizing, "pv"), 4),
        "battery_kwh": round(_sz(result.sizing, "battery_energy"), 4),
        "inverter_kw": round(_sz(result.sizing, "inverter"), 4),
        "annual_pv_kwh": round(k.get("total_pv_generation", 0.0), 2),
        "renewable_fraction": round(k.get("renewable_fraction", 0.0), 6),
        "annual_diesel_l": round(k.get("dg_fuel_consumption_liters", 0.0), 2),
        "total_grid_bought": round(k.get("total_grid_bought", 0.0), 2),
        "total_grid_cost_net": round(k.get("total_grid_cost_net", 0.0), 2),
        "lpsp": round(k.get("lpsp", 0.0), 6),
        # v4 KPIs
        "annual_demand_charge_usd": round(k.get("annual_demand_charge_usd", 0.0), 2),
        "annual_energy_net_usd": round(k.get("annual_energy_net_usd", 0.0), 2),
        "annual_throughput_cycles": round(k.get("annual_throughput_cycles", 0.0), 4),
        "battery_eol_year": int(k.get("battery_eol_year", 0)),
    }
    tolerances: dict[str, dict[str, Any]] = {}
    for key, val in kpis.items():
        if key in ("pv_kw", "battery_kwh", "inverter_kw", "annual_diesel_l", "lpsp"):
            tolerances[key] = dict(_ABS) if abs(val) < 1.0 else dict(_REL)
        elif key == "battery_eol_year":
            tolerances[key] = {"type": "absolute", "value": 0.5}
        elif abs(val) < 1.0:
            tolerances[key] = dict(_ABS)
        else:
            tolerances[key] = dict(_REL)

    reference = {
        "scenario": name,
        "source": "samba_lp",
        "samba_version": samba.__version__,
        "description": f"v4 golden: {name}",
        "kpis": kpis,
        "series_kpis": {
            "peak_demand_kw_by_month": [round(v, 4) for v in k.get("peak_demand_kw_by_month", [])],
        },
        "tolerances": tolerances,
    }
    (sd / "reference.json").write_text(json.dumps(reference, indent=2) + "\n", encoding="utf-8")
    msg = f"  {name}: npc={kpis['npc']}  pv_kw={kpis['pv_kw']}  demand={kpis['annual_demand_charge_usd']}"  # noqa: E501
    print(msg)


if __name__ == "__main__":
    for d in DIRS:
        print(f"Running {d} ...", flush=True)
        capture(d)
    print("done")
