# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""v2 feature-specific golden scenario tests.

Each test in this module covers one of the six v2 golden scenarios (g07–g12)
and verifies **semantic invariants** that go beyond simple KPI-tolerance checks:

* g07 — Multi-objective: emissions_weight=50 → near-zero diesel usage
* g08 — DG economics: LP DG golden; DG is the dominant energy source
* g09 — EV smart charge (no V2G): EV charges, zero V2G revenue
* g10 — EV V2G enabled: positive V2G revenue, negative NPC (profit scenario)
* g11 — KiBaM battery: correct chemistry sizing, off-grid feasibility
* g12 — Endogenous tiered tariff: monthly grid sums are consistent

These tests are tagged ``@pytest.mark.benchmark`` (slow, require solver) and
are skipped by the fast unit-test suite::

    pytest tests/goldens/ -m benchmark -k v2        # only v2 goldens
    pytest tests/goldens/ -m "not benchmark"        # skip all benchmark tests
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import samba
from samba.input_resolver import resolve_arrays

from .conftest import (
    GOLDENS_DIR,
    assert_within_tolerance,
    load_golden_scenario,
    load_reference,
)

# ---------------------------------------------------------------------------
# Helpers — extended KPI extraction for v2 features
# ---------------------------------------------------------------------------


def _extract_v2_kpis(result: Any) -> dict[str, Any]:
    """Extract KPIs from a :func:`samba.run` result, including v2 extras.

    Returns a flat dict with all keys used in g07–g12 reference.json files,
    plus a ``monthly_grid_kwh`` list for g12.
    """
    kpis: dict[str, Any] = {}

    # Core scalar KPIs (always present)
    kpis["npc"] = float(result.kpis.get("npc", 0.0))
    kpis["lcoe"] = float(result.kpis.get("lcoe", 0.0))
    kpis["annual_pv_kwh"] = float(result.kpis.get("total_pv_generation", 0.0))
    kpis["renewable_fraction"] = float(result.kpis.get("renewable_fraction", 0.0))
    kpis["annual_diesel_l"] = float(result.kpis.get("dg_fuel_consumption_liters", 0.0))
    kpis["lpsp"] = float(result.kpis.get("lpsp", 0.0))

    # v2 extras
    kpis["total_grid_bought"] = float(result.kpis.get("total_grid_bought", 0.0))
    kpis["total_grid_cost_net"] = float(result.kpis.get("total_grid_cost_net", 0.0))
    kpis["annual_ev_charge_kwh"] = float(result.kpis.get("annual_ev_charge_kwh", 0.0))
    kpis["annual_ev_discharge_kwh"] = float(result.kpis.get("annual_ev_discharge_kwh", 0.0))
    kpis["ev_v2g_revenue"] = float(result.kpis.get("ev_v2g_revenue", 0.0))
    kpis["total_emissions_kg"] = float(result.kpis.get("total_emissions_kg", 0.0))
    kpis["dg_operating_hours"] = int(result.kpis.get("dg_operating_hours", 0))

    # Monthly grid kWh list (may be absent for off-grid scenarios)
    monthly_raw = result.kpis.get("monthly_grid_kwh", None)
    if monthly_raw is not None:
        kpis["monthly_grid_kwh"] = [float(v) for v in monthly_raw]

    # Sizing
    sizing = result.sizing
    if sizing is not None and not sizing.empty:
        pv_rows = sizing[sizing["component"] == "pv"]
        bat_rows = sizing[sizing["component"] == "battery_energy"]
        inv_rows = sizing[sizing["component"] == "inverter"]
        kpis["pv_kw"] = float(pv_rows["capacity"].sum()) if not pv_rows.empty else 0.0
        kpis["battery_kwh"] = float(bat_rows["capacity"].sum()) if not bat_rows.empty else 0.0
        kpis["inverter_kw"] = float(inv_rows["capacity"].sum()) if not inv_rows.empty else 0.0
    else:
        kpis["pv_kw"] = 0.0
        kpis["battery_kwh"] = 0.0
        kpis["inverter_kw"] = 0.0

    return kpis


def _scenario_dir(name: str) -> Path:
    return GOLDENS_DIR / name


# ---------------------------------------------------------------------------
# g07 — Multi-objective (cost + emissions)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g07_multi_objective_kpis_and_invariants() -> None:
    """g07: multi-objective with emissions_weight=50 → near-zero diesel, high RE fraction."""
    scenario_dir = _scenario_dir("g07_multi_objective")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        output_dir=None,
    )

    kpis = _extract_v2_kpis(result)
    assert_within_tolerance(kpis, reference)

    # v2 invariants
    rf = kpis["renewable_fraction"]
    assert rf > 0.99, f"g07: emissions_weight=50 should push RE fraction >99%; got {rf:.4f}"
    diesel_l = kpis["annual_diesel_l"]
    assert diesel_l < 500, (
        f"g07: emissions_weight=50 should suppress diesel <500 L/yr; got {diesel_l:.1f}"
    )
    em_kg = kpis["total_emissions_kg"]
    assert em_kg < 1500, (
        f"g07: expected low total_emissions_kg with carbon penalty; got {em_kg:.1f}"
    )
    assert kpis["pv_kw"] > 5.0, (
        f"g07: large PV expected to displace diesel; got pv_kw={kpis['pv_kw']:.2f}"
    )


# ---------------------------------------------------------------------------
# g08 — DG unit commitment (LP, economics golden)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g08_dg_economics_kpis_and_invariants() -> None:
    """g08: LP DG golden — diesel dominates, positive emissions, DG hours > 0."""
    scenario_dir = _scenario_dir("g08_dg_unit_commitment")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        output_dir=None,
    )

    kpis = _extract_v2_kpis(result)
    assert_within_tolerance(kpis, reference)

    # v2 invariants — DG feature sanity
    assert kpis["annual_diesel_l"] > 1000, (
        f"g08: DG should consume significant fuel; got {kpis['annual_diesel_l']:.1f} L"
    )
    assert kpis["total_emissions_kg"] > 1000, (
        f"g08: DG emissions should be significant; got {kpis['total_emissions_kg']:.1f} kg"
    )
    assert kpis["dg_operating_hours"] > 0, (
        f"g08: DG should be running; got dg_operating_hours={kpis['dg_operating_hours']}"
    )
    assert kpis["lpsp"] < 0.01, f"g08: off-grid LPSP should be ~0; got lpsp={kpis['lpsp']:.4f}"


# ---------------------------------------------------------------------------
# g09 — EV smart charging (V2G disabled)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g09_ev_smart_charge_kpis_and_invariants() -> None:
    """g09: TOU smart charging, no V2G — ev_v2g_revenue == 0, EV charges correctly."""
    scenario_dir = _scenario_dir("g09_ev_smart_charge")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        output_dir=None,
    )

    kpis = _extract_v2_kpis(result)
    assert_within_tolerance(kpis, reference)

    # v2 invariants
    assert kpis["annual_ev_charge_kwh"] > 1000, (
        f"g09: EV must charge during the year; got {kpis['annual_ev_charge_kwh']:.1f} kWh"
    )
    assert kpis["ev_v2g_revenue"] < 1.0, (
        f"g09: V2G disabled → revenue must be ~0; got {kpis['ev_v2g_revenue']:.2f}"
    )
    ev_dis = kpis["annual_ev_discharge_kwh"]
    assert ev_dis < 1.0, f"g09: V2G disabled → EV discharge to grid must be ~0; got {ev_dis:.2f}"
    assert kpis["total_grid_bought"] > 0, (
        f"g09: grid must supply energy; got total_grid_bought={kpis['total_grid_bought']:.1f}"
    )


# ---------------------------------------------------------------------------
# g10 — EV V2G enabled
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g10_ev_v2g_kpis_and_invariants() -> None:
    """g10: V2G enabled — significant V2G revenue, negative NPC, EV discharges."""
    scenario_dir = _scenario_dir("g10_ev_v2g")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        output_dir=None,
    )

    kpis = _extract_v2_kpis(result)
    assert_within_tolerance(kpis, reference)

    # v2 invariants — V2G feature sanity
    assert kpis["ev_v2g_revenue"] > 5000, (
        f"g10: V2G sell revenue should exceed £5000/yr; got {kpis['ev_v2g_revenue']:.2f}"
    )
    ev_dis_v2g = kpis["annual_ev_discharge_kwh"]
    assert ev_dis_v2g > 10000, (
        f"g10: EV must discharge substantial energy for V2G; got {ev_dis_v2g:.1f} kWh"
    )
    assert kpis["npc"] < 0, (
        f"g10: V2G revenue should outweigh costs → NPC < 0; got npc={kpis['npc']:.2f}"
    )
    # V2G revenue must strictly exceed no-V2G case (g09 ev_v2g_revenue == 0)
    assert kpis["ev_v2g_revenue"] > 0, (
        f"g10: ev_v2g_revenue must be positive; got {kpis['ev_v2g_revenue']:.2f}"
    )


# ---------------------------------------------------------------------------
# g11 — KiBaM battery
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g11_kibam_battery_kpis_and_invariants() -> None:
    """g11: KiBaM lead-acid battery — off-grid feasibility, large battery sizing."""
    scenario_dir = _scenario_dir("g11_kibam_battery")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        output_dir=None,
    )

    kpis = _extract_v2_kpis(result)
    assert_within_tolerance(kpis, reference)

    # v2 invariants — KiBaM chemistry
    assert kpis["battery_kwh"] > 50, (
        "g11: KiBaM DoD restriction (soc_min=0.40) + c-rate limit should "
        f"require large battery; got {kpis['battery_kwh']:.1f} kWh"
    )
    assert kpis["lpsp"] < 0.01, (
        f"g11: off-grid must be feasible (lpsp<1%); got lpsp={kpis['lpsp']:.4f}"
    )
    assert kpis["renewable_fraction"] > 0.95, (
        f"g11: PV+KiBaM off-grid should be 100% RE; got {kpis['renewable_fraction']:.4f}"
    )
    assert kpis["annual_diesel_l"] < 10, (
        f"g11: no diesel generator in this scenario; got {kpis['annual_diesel_l']:.1f} L"
    )
    assert kpis["total_grid_bought"] < 0.1, (
        f"g11: off-grid — no grid energy; got {kpis['total_grid_bought']:.2f} kWh"
    )


# ---------------------------------------------------------------------------
# g12 — Endogenous tiered tariff
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g12_tiered_tariff_endogenous_kpis_and_invariants() -> None:
    """g12: endogenous 3-tier tariff — monthly grid sums are consistent with annual total."""
    scenario_dir = _scenario_dir("g12_tiered_tariff_endogenous")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        output_dir=None,
    )

    kpis = _extract_v2_kpis(result)
    assert_within_tolerance(kpis, reference)

    # v2 invariants — endogenous tariff feature
    assert kpis["total_grid_cost_net"] > 0, (
        f"g12: tiered grid cost must be positive; got {kpis['total_grid_cost_net']:.2f}"
    )
    assert kpis["total_grid_bought"] > 0, (
        f"g12: grid must supply energy; got {kpis['total_grid_bought']:.1f} kWh"
    )
    assert kpis["pv_kw"] > 0, f"g12: PV is installed (fixed 2 kW); got {kpis['pv_kw']:.2f}"

    # Monthly grid sum must equal annual total (within floating point tolerance)
    if "monthly_grid_kwh" in kpis:
        monthly_sum = sum(kpis["monthly_grid_kwh"])
        annual_total = kpis["total_grid_bought"]
        rel_error = abs(monthly_sum - annual_total) / max(abs(annual_total), 1e-6)
        assert rel_error < 0.02, (
            f"g12: sum(monthly_grid_kwh)={monthly_sum:.2f} should match "
            f"total_grid_bought={annual_total:.2f} (got {rel_error:.1%} discrepancy)"
        )

    # Battery is present (fixed 20 kWh for arbitrage)
    assert kpis["battery_kwh"] > 5, (
        f"g12: fixed 20 kWh battery should be present; got {kpis['battery_kwh']:.2f} kWh"
    )
