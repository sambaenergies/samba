# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Sweep PV capacity from 0 to 20 kW (fixed, not Investment) for g01.

For each PV size, solve the LP and record:
- LP objective value (total annual $ in the model)
- grid_buy, grid_sell, energy_dump
- inv_kw (from invest sizing)

This reveals the true economic optimum and diagnoses whether the Investment
LP is converging to the right answer.

Run:
    .venv/Scripts/python.exe scripts/diag_pv_sweep.py \
        2>&1 | Tee-Object scripts/diag_pv_sweep_out.txt
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONUTF8", "1")

repo = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo))

import logging  # noqa: E402

logging.disable(logging.CRITICAL)  # silence oemof/pyomo logs

import numpy as np  # noqa: E402

from samba.compiler import CompilerInputs, compile_energy_system  # noqa: E402
from samba.compiler.annualize import ep_costs, real_discount_rate  # noqa: E402
from samba.input_resolver import resolve_arrays  # noqa: E402
from samba.scenario import load_scenario  # noqa: E402
from samba.solver.extract import extract_dispatch  # noqa: E402
from samba.solver.runner import SolverConfig, solve  # noqa: E402
from samba.tariff import resolve_tariff  # noqa: E402
from samba.weather import stub_weather  # noqa: E402

goldens = repo / "tests" / "goldens"
scenario_dir = goldens / "g01_grid_pv_batt"

scenario = load_scenario(scenario_dir / "scenario.yaml")
load_kw, pv_per_kwp, _ = resolve_arrays(scenario, scenario_dir)
tariff_arrays = resolve_tariff(scenario.tariff, load_kw, scenario.project.year)

proj = scenario.project
comps = scenario.components
assert comps.pv is not None, "g01 scenario must have a PV component"
assert comps.battery is not None, "g01 scenario must have a Battery component"
assert pv_per_kwp is not None, "resolve_arrays must return PV irradiance array"

r_real = real_discount_rate(proj.discount_rate_nominal, proj.inflation_rate)
pv_ep = ep_costs(
    comps.pv.capex_per_kw * (1 - proj.re_incentive_rate), r_real, comps.pv.lifetime_years
)
inv_ep = ep_costs(comps.inverter.capex_per_kw, r_real, comps.inverter.lifetime_years)

print(f"PV ep_costs  = {pv_ep:.4f} $/kW/yr (real rate {r_real * 100:.4f}%)")
print(f"Inv ep_costs = {inv_ep:.4f} $/kW/yr")
print(f"PV yield     = {np.sum(pv_per_kwp):.1f} kWh/kWp/yr")
print()

config = SolverConfig()

# -- Investment mode solve (what SAMBA currently does) ----------------------
print("=== Investment mode solve ===")
es_invest = compile_energy_system(
    CompilerInputs(
        scenario=scenario,
        load_kw=load_kw,
        tariff_arrays=tariff_arrays,
        weather=stub_weather(),
        pv_per_kwp=pv_per_kwp,
    )
)
raw = solve(es_invest, scenario, config)
dr = extract_dispatch(es_invest, raw)
caps = dr.capacities
dispatch = dr.dispatch
grid_net = float(
    np.sum(dispatch["grid_buy"].values * tariff_arrays.cbuy)
    - np.sum(dispatch["grid_sell"].values * tariff_arrays.csell)
)
pv_cap = caps.get("pv_kw", 0.0)
inv_cap = caps.get("inverter_kw", 0.0)
lp_obj_invest = pv_ep * pv_cap + inv_ep * inv_cap + grid_net
rf = float(dispatch["pv_gen"].sum()) / (
    float(dispatch["pv_gen"].sum()) + float(dispatch["grid_buy"].sum())
)
print(f"  pv_kw={pv_cap:.3f}  inv_kw={inv_cap:.3f}  grid_net={grid_net:.2f}  RF={rf:.4f}")
print(f"  LP_obj_value = {lp_obj_invest:.2f} $/yr  (capital + grid)")
print()

# -- Fixed PV sweep ---------------------------------------------------------

import copy  # noqa: E402


def solve_fixed_pv(pv_kw: float, inv_kw: float | None = None) -> dict[str, Any]:
    """Solve with PV and inverter fixed at given capacities (no Investment)."""

    # Deep-copy scenario and override pv capacity + inverter
    sc2 = copy.deepcopy(scenario)
    assert sc2.components.pv is not None
    assert sc2.components.battery is not None
    assert pv_per_kwp is not None
    sc2.components.pv.capacity_kw = pv_kw
    # Set inverter to fixed also -- use peak PV output as size
    peak_pv_dc = pv_kw * float(np.max(pv_per_kwp))
    sc2.components.inverter.capacity_kw = inv_kw if inv_kw is not None else peak_pv_dc * 0.96
    # battery stays in investment mode (or fix at 0 for clean test)
    sc2.components.battery.capacity_kwh = 0.001  # near-zero fixed

    es2 = compile_energy_system(
        CompilerInputs(
            scenario=sc2,
            load_kw=load_kw,
            tariff_arrays=tariff_arrays,
            weather=stub_weather(),
            pv_per_kwp=pv_per_kwp,
        )
    )
    try:
        raw2 = solve(es2, sc2, config)
    except Exception as e:
        return {"error": str(e)}

    dr2 = extract_dispatch(es2, raw2)
    d2 = dr2.dispatch

    grid_buy = float(d2["grid_buy"].sum())
    grid_sell = float(d2["grid_sell"].sum())
    pv_dc = float(d2["pv_gen"].sum())
    grid_net2 = float(
        np.sum(d2["grid_buy"].values * tariff_arrays.cbuy)
        - np.sum(d2["grid_sell"].values * tariff_arrays.csell)
    )
    dump = float(d2["energy_dump"].sum())
    inv_size = peak_pv_dc * 0.96 if inv_kw is None else inv_kw

    # LP objective (fixed PV has no ep_costs contribution; inv is also fixed)
    full_cost = pv_ep * pv_kw + inv_ep * inv_size + grid_net2  # "as if investment"

    rf2 = pv_dc / (pv_dc + grid_buy) if (pv_dc + grid_buy) > 0 else 0
    return {
        "pv_kw": pv_kw,
        "inv_kw": inv_size,
        "grid_buy": grid_buy,
        "grid_sell": grid_sell,
        "pv_dc": pv_dc,
        "dump": dump,
        "grid_net": grid_net2,
        "full_cost": full_cost,
        "rf": rf2,
    }


print("=== Fixed PV sweep (inv = peak PV output) ===")
print(
    f"{'pv_kw':>8} {'inv_kw':>8} {'pv_dc':>10} {'grid_buy':>10} {'grid_sell':>10} "
    f"{'dump':>8} {'grid_net':>10} {'full_cost':>11} {'RF':>6}"
)
print("-" * 90)

sweep = [
    0.5,
    1.0,
    2.0,
    3.0,
    3.17,
    4.0,
    5.0,
    6.0,
    7.0,
    8.0,
    9.0,
    10.0,
    11.0,
    11.56,
    12.0,
    14.0,
    16.0,
    20.0,
]
results = []
for pv in sweep:
    r = solve_fixed_pv(pv)
    if "error" in r:
        print(f"  pv={pv:.2f}: ERROR {r['error']}")
        continue
    results.append(r)
    print(
        f"{r['pv_kw']:>8.2f} {r['inv_kw']:>8.3f} {r['pv_dc']:>10.1f} "
        f"{r['grid_buy']:>10.1f} {r['grid_sell']:>10.1f} "
        f"{r['dump']:>8.1f} {r['grid_net']:>10.2f} "
        f"{r['full_cost']:>11.2f} {r['rf']:>6.4f}"
    )

if results:
    best = min(results, key=lambda r: r["full_cost"])
    print()
    print(
        f"*** Minimum full_cost at pv_kw = {best['pv_kw']:.2f} kW: {best['full_cost']:.2f} $/yr ***"
    )
    print(
        f"    (Investment mode found:  pv_kw = {pv_cap:.3f} kW, full_cost ~= {lp_obj_invest:.2f} $/yr)"  # noqa: E501
    )
    print()
    if abs(best["pv_kw"] - pv_cap) > 0.5:
        print("!! DISCREPANCY: Investment LP optimum differs from fixed-PV sweep optimum !!")
        print("!! The LP Investment formulation is NOT finding the true economic optimum !!")
    else:
        print("OK: Investment LP matches sweep optimum.")
