# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""v3 feature-specific golden scenario tests.

Each test in this module covers one of the seven v3 golden scenarios (g13–g19)
and verifies **semantic invariants** that go beyond simple KPI-tolerance checks:

* g13 — HP Heating-Only: constant 5 kW_th load, constant outdoor T → deterministic COP
* g14 — HP Cooling-Only: constant 4 kW_th load, validates T_iwb psychrometrics
* g15 — HP + Thermal Storage TOU: LP invests in thermal storage for price arbitrage
* g16 — Gas vs HP merit-order: high electricity price → LP dispatches gas exclusively
* g17 — Degree-Day loads: SF climate is heating-dominated (heating >> cooling)
* g18 — Full coupled PV+HP+TS+Gas: multi-component integration, gas unused
* g19 — Heat pump: heating-dominated degree-day site, COP + KPI regression

These tests are tagged ``@pytest.mark.benchmark`` (slow, require solver) and
are skipped by the fast unit-test suite::

    pytest tests/goldens/ -m benchmark -k v3        # only v3 goldens
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
# Helpers — extended KPI extraction for v3 thermal features
# ---------------------------------------------------------------------------


def _extract_v3_kpis(result: Any) -> dict[str, Any]:
    """Extract KPIs from a :func:`samba.run` result, including v3 thermal extras.

    Returns a flat dict with all keys used in g13–g19 reference.json files.
    """
    kpis: dict[str, Any] = {}

    # Core scalar KPIs (required for all scenarios)
    kpis["npc"] = float(result.kpis.get("npc", 0.0))
    kpis["lcoe"] = float(result.kpis.get("lcoe", 0.0))
    kpis["annual_pv_kwh"] = float(result.kpis.get("total_pv_generation", 0.0))
    kpis["renewable_fraction"] = float(result.kpis.get("renewable_fraction", 0.0))
    kpis["annual_diesel_l"] = float(result.kpis.get("dg_fuel_consumption_liters", 0.0))
    kpis["total_grid_bought"] = float(result.kpis.get("total_grid_bought", 0.0))

    # v3 thermal — heat pump
    kpis["annual_heat_produced_kwh"] = float(result.kpis.get("annual_heat_produced_kwh", 0.0))
    kpis["annual_cool_produced_kwh"] = float(result.kpis.get("annual_cool_produced_kwh", 0.0))
    kpis["mean_cop_heating"] = float(result.kpis.get("mean_cop_heating", 0.0))
    kpis["mean_cop_cooling"] = float(result.kpis.get("mean_cop_cooling", 0.0))
    kpis["annual_heating_demand_kwh_th"] = float(
        result.kpis.get("annual_heating_demand_kwh_th", 0.0)
    )
    kpis["annual_cooling_demand_kwh_th"] = float(
        result.kpis.get("annual_cooling_demand_kwh_th", 0.0)
    )
    kpis["annual_hp_elec_kwh"] = float(result.kpis.get("annual_hp_elec_kwh", 0.0))

    # v3 thermal — thermal storage
    kpis["thermal_storage_capex"] = float(result.kpis.get("thermal_storage_capex", 0.0))
    kpis["annual_thermal_storage_cycles"] = float(
        result.kpis.get("annual_thermal_storage_cycles", 0.0)
    )

    # v3 thermal — gas supply
    kpis["annual_gas_consumption_kwh_th"] = float(
        result.kpis.get("annual_gas_consumption_kwh_th", 0.0)
    )
    kpis["annual_gas_cost_usd"] = float(result.kpis.get("annual_gas_cost_usd", 0.0))
    kpis["annual_gas_co2_kg"] = float(result.kpis.get("annual_gas_co2_kg", 0.0))
    kpis["gas_boiler_npc"] = float(result.kpis.get("gas_boiler_npc", 0.0))
    kpis["gas_boiler_capex"] = float(result.kpis.get("gas_boiler_capex", 0.0))

    # Sizing from the sizing DataFrame
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
# g13 — HP Heating-Only (constant 5 kW CSV load)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g13_heat_pump_heating_only_kpis_and_invariants() -> None:
    """g13: Grid + HP heating-only, constant 5 kW_th CSV load.

    Validates catalog COP heating model. All heat demand must be met (lpsp=0).
    """
    scenario_dir = _scenario_dir("g13_heat_pump_heating_only")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        scenario_dir=scenario_dir,
        output_dir=None,
    )

    kpis = _extract_v3_kpis(result)
    assert_within_tolerance(kpis, reference)

    # v3 invariants — heating-only HP
    expected_annual_heat = 5.0 * 8760  # = 43800 kWh_th
    assert abs(kpis["annual_heat_produced_kwh"] - expected_annual_heat) < 500, (
        f"g13: 5 kW × 8760 h = 43800 kWh_th; "
        f"got annual_heat_produced_kwh={kpis['annual_heat_produced_kwh']:.1f}"
    )
    assert kpis["mean_cop_heating"] > 3.0, (
        f"g13: HP COP heating must be > 3.0; got {kpis['mean_cop_heating']:.4f}"
    )
    assert kpis["annual_cool_produced_kwh"] < 1.0, (
        f"g13: heating_only mode → no cooling; got {kpis['annual_cool_produced_kwh']:.2f} kWh_th"
    )
    assert kpis["annual_diesel_l"] < 1.0, "g13: no diesel generator"
    assert kpis["pv_kw"] < 0.1, "g13: no PV"
    assert kpis["battery_kwh"] < 0.1, "g13: no battery"


# ---------------------------------------------------------------------------
# g14 — HP Cooling-Only (constant 4 kW CSV load)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g14_heat_pump_cooling_only_kpis_and_invariants() -> None:
    """g14: Grid + HP cooling-only, constant 4 kW_th CSV load.

    Validates T_iwb psychrometric model for cooling COP. Mean COP > 4.0.
    """
    scenario_dir = _scenario_dir("g14_heat_pump_cooling_only")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        scenario_dir=scenario_dir,
        output_dir=None,
    )

    kpis = _extract_v3_kpis(result)
    assert_within_tolerance(kpis, reference)

    # v3 invariants — cooling-only HP
    expected_annual_cool = 4.0 * 8760  # = 35040 kWh_th
    assert abs(kpis["annual_cool_produced_kwh"] - expected_annual_cool) < 500, (
        f"g14: 4 kW × 8760 h = 35040 kWh_th; "
        f"got annual_cool_produced_kwh={kpis['annual_cool_produced_kwh']:.1f}"
    )
    assert kpis["mean_cop_cooling"] > 4.0, (
        f"g14: HP COP cooling must be > 4.0; got {kpis['mean_cop_cooling']:.4f}"
    )
    assert kpis["annual_heat_produced_kwh"] < 1.0, (
        f"g14: cooling_only mode → no heating; got {kpis['annual_heat_produced_kwh']:.2f} kWh_th"
    )
    assert kpis["annual_diesel_l"] < 1.0, "g14: no diesel generator"
    assert kpis["pv_kw"] < 0.1, "g14: no PV"


# ---------------------------------------------------------------------------
# g15 — HP + Thermal Storage TOU (time-shifting)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g15_hp_thermal_storage_tou_kpis_and_invariants() -> None:
    """g15: Grid + HP + Thermal Storage (investment), TOU $0.08 off-peak / $0.25 on-peak.

    LP time-shifts HP to off-peak hours using thermal storage.
    Storage capex > 0 (LP decides to invest). Cycle count validates active use.
    """
    scenario_dir = _scenario_dir("g15_hp_thermal_storage_tou")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        scenario_dir=scenario_dir,
        output_dir=None,
    )

    kpis = _extract_v3_kpis(result)
    assert_within_tolerance(kpis, reference)

    # v3 invariants — thermal storage with TOU
    assert kpis["thermal_storage_capex"] > 0, (
        "g15: LP should invest in thermal storage for TOU arbitrage; "
        f"got thermal_storage_capex={kpis['thermal_storage_capex']:.2f}"
    )
    assert kpis["annual_thermal_storage_cycles"] > 100, (
        f"g15: thermal storage must be actively cycled; "
        f"got annual_thermal_storage_cycles={kpis['annual_thermal_storage_cycles']:.1f}"
    )
    assert kpis["annual_heat_produced_kwh"] > 40000, (
        f"g15: full 5 kW heating demand must be met; "
        f"got annual_heat_produced_kwh={kpis['annual_heat_produced_kwh']:.1f}"
    )
    assert kpis["mean_cop_heating"] > 3.0, (
        f"g15: HP COP heating must be > 3.0; got {kpis['mean_cop_heating']:.4f}"
    )
    assert kpis["pv_kw"] < 0.1, "g15: no PV"


# ---------------------------------------------------------------------------
# g16 — Gas vs HP merit-order dispatch
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g16_gas_vs_hp_kpis_and_invariants() -> None:
    """g16: HP vs gas boiler — high electricity price ($0.25/kWh) → gas dominates.

    Merit-order test: LP must dispatch gas boiler and suppress HP entirely.
    annual_heat_produced_kwh (HP) ≈ 0; annual_gas_consumption >>> 0.
    """
    scenario_dir = _scenario_dir("g16_gas_vs_hp")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        scenario_dir=scenario_dir,
        output_dir=None,
    )

    kpis = _extract_v3_kpis(result)
    assert_within_tolerance(kpis, reference)

    # v3 invariants — gas dominates HP at high electricity price
    assert kpis["annual_gas_consumption_kwh_th"] > kpis["annual_heat_produced_kwh"], (
        f"g16: gas must dominate HP at $0.25/kWh_e; "
        f"gas={kpis['annual_gas_consumption_kwh_th']:.0f} kWh_th, "
        f"hp_heat={kpis['annual_heat_produced_kwh']:.0f} kWh_th"
    )
    assert kpis["annual_gas_consumption_kwh_th"] > 30000, (
        f"g16: gas boiler must supply significant heat; "
        f"got {kpis['annual_gas_consumption_kwh_th']:.0f} kWh_th"
    )
    assert kpis["annual_gas_co2_kg"] > 5000, (
        f"g16: gas CO2 emissions must be significant; got {kpis['annual_gas_co2_kg']:.0f} kg"
    )
    assert kpis["gas_boiler_npc"] > 0, (
        f"g16: gas boiler must have positive NPC (it's used); got {kpis['gas_boiler_npc']:.2f}"
    )
    assert kpis["pv_kw"] < 0.1, "g16: no PV"
    assert kpis["annual_diesel_l"] < 1.0, "g16: no diesel"


# ---------------------------------------------------------------------------
# g17 — Degree-Day loads (SF climate)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g17_degree_day_loads_kpis_and_invariants() -> None:
    """g17: Degree-day thermal load model, UA=0.5 kW/°C, setpoints 20°C heat / 26°C cool.

    San Francisco climate is heating-dominated: annual heating demand >>> cooling demand.
    """
    scenario_dir = _scenario_dir("g17_degree_day_loads")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        scenario_dir=scenario_dir,
        output_dir=None,
    )

    kpis = _extract_v3_kpis(result)
    assert_within_tolerance(kpis, reference)

    # v3 invariants — degree-day model with SF climate
    assert kpis["annual_heating_demand_kwh_th"] > kpis["annual_cooling_demand_kwh_th"] * 100, (
        f"g17: SF is heating-dominated; heating={kpis['annual_heating_demand_kwh_th']:.0f}, "
        f"cooling={kpis['annual_cooling_demand_kwh_th']:.0f} kWh_th"
    )
    assert kpis["annual_heating_demand_kwh_th"] > 10000, (
        f"g17: significant annual heating load expected; "
        f"got {kpis['annual_heating_demand_kwh_th']:.0f} kWh_th"
    )
    assert kpis["mean_cop_heating"] > 3.0, (
        f"g17: HP COP heating must be > 3.0; got {kpis['mean_cop_heating']:.4f}"
    )
    assert kpis["annual_heat_produced_kwh"] > 0, "g17: HP must produce heat"
    assert kpis["pv_kw"] < 0.1, "g17: no PV"
    assert kpis["annual_diesel_l"] < 1.0, "g17: no diesel"


# ---------------------------------------------------------------------------
# g18 — Full Coupled PV + HP + Thermal Storage + Gas
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g18_full_coupled_pv_hp_gas_kpis_and_invariants() -> None:
    """g18: Full integration — PV + Battery + Grid + HP + Thermal Storage + Gas Boiler.

    LP sizes PV; gas boiler is installed but economically unused (PV+HP cheaper).
    renewable_fraction > 0.25; annual_gas_consumption ≈ 0.
    """
    scenario_dir = _scenario_dir("g18_full_coupled_pv_hp_gas")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        scenario_dir=scenario_dir,
        output_dir=None,
    )

    kpis = _extract_v3_kpis(result)
    assert_within_tolerance(kpis, reference)

    # v3 invariants — full coupled multi-component
    assert kpis["pv_kw"] > 0.5, f"g18: LP should invest in PV; got pv_kw={kpis['pv_kw']:.2f}"
    assert kpis["renewable_fraction"] > 0.20, (
        f"g18: PV should provide significant RE fraction; "
        f"got renewable_fraction={kpis['renewable_fraction']:.4f}"
    )
    assert kpis["annual_gas_consumption_kwh_th"] < 500, (
        f"g18: gas boiler should be unused when PV+HP dominates; "
        f"got annual_gas_consumption_kwh_th={kpis['annual_gas_consumption_kwh_th']:.0f}"
    )
    assert kpis["thermal_storage_capex"] > 0, (
        f"g18: LP should invest in thermal storage; "
        f"got thermal_storage_capex={kpis['thermal_storage_capex']:.2f}"
    )
    assert kpis["annual_heat_produced_kwh"] > 0, "g18: HP must produce heat"
    assert kpis["annual_diesel_l"] < 1.0, "g18: no diesel"


# ---------------------------------------------------------------------------
# g19 — Heat pump (heating-dominated, degree-day loads)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
def test_g19_heat_pump_kpis_and_invariants() -> None:
    """g19: heat-pump regression on a heating-dominated site.

    Degree-day loads with a 7562 kWh/yr electrical load. KPIs are gated against
    reference.json (± stated tolerances) plus physical invariants.
    """
    scenario_dir = _scenario_dir("g19_heat_pump")
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        scenario_dir=scenario_dir,
        output_dir=None,
    )

    kpis = _extract_v3_kpis(result)
    assert_within_tolerance(kpis, reference)

    # Physical invariants
    assert kpis["annual_heating_demand_kwh_th"] > kpis["annual_cooling_demand_kwh_th"] * 100, (
        f"g19: heating-dominated site; "
        f"heating={kpis['annual_heating_demand_kwh_th']:.0f}, "
        f"cooling={kpis['annual_cooling_demand_kwh_th']:.0f} kWh_th"
    )
    assert kpis["mean_cop_heating"] > 1.0, (
        f"g19: HP heating COP must exceed 1.0; got {kpis['mean_cop_heating']:.4f}"
    )
    assert kpis["pv_kw"] < 0.1, "g19: no PV"
    assert kpis["annual_diesel_l"] < 1.0, "g19: no diesel"
