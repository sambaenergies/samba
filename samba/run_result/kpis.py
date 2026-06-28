# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""KPI computation and result assembly.

This module is the top-level entry point for converting a solved
:class:'~samba.solver.extract.DispatchResult' into the three primary result
artifacts:

* ''kpis.json''   -- :func:'compute_kpis' -> ''dict''
* ''economics.json'' -- :func:'compute_kpis' -> ''dict''
* ''sizing.csv''  -- :func:'compute_kpis' -> ''pd.DataFrame''

All schemas are authoritative from ''docs/developer/results-contract.md''.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from samba._kpi_contract import KPI_CONTRACT_VERSION
from samba.compiler.annualize import crf as _crf
from samba.economics.cashflow import (
    _attr,  # private helper re-used here
    _get_battery_kwh,
    _get_inverter_kw,
    _get_pv_kw,
    build_economics,
)
from samba.economics.emissions import (
    DEFAULT_DG_EMISSION_FACTOR,
    DEFAULT_GRID_EMISSION_FACTOR,
    dg_emissions_kg,
    dg_fuel_liters,
    grid_emissions_kg,
)
from samba.economics.npc import real_discount_rate

if TYPE_CHECKING:
    from samba.scenario.models import Scenario
    from samba.solver.extract import DispatchResult
    from samba.tariff.resolver import TariffArrays

__all__ = ["compute_kpis"]


def _energy_statistics(dispatch: pd.DataFrame, tariff_arrays: TariffArrays) -> dict[str, float]:
    """Return core electrical and EV energy statistics from dispatch."""
    total_load_served = float(dispatch["eload"].sum())
    total_unmet_load = float(dispatch["unmet_load"].sum())
    total_demand = total_load_served + total_unmet_load
    lpsp = total_unmet_load / total_demand if total_demand > 0.0 else 0.0

    total_pv_generation = float(dispatch["pv_gen"].sum())
    total_wt_generation = float(dispatch["wt_gen"].sum())
    total_dg_generation = float(dispatch["dg_gen"].sum())
    total_grid_bought = float(dispatch["grid_buy"].sum())
    total_grid_sold = float(dispatch["grid_sell"].sum())
    total_energy_dump = float(dispatch["energy_dump"].sum())
    total_battery_charge = float(dispatch["batt_charge"].sum())
    total_battery_discharge = float(dispatch["batt_discharge"].sum())
    total_ev_charge = (
        float(dispatch["ev_charge_kw"].sum()) if "ev_charge_kw" in dispatch.columns else 0.0
    )
    total_ev_discharge = (
        float(dispatch["ev_discharge_kw"].sum()) if "ev_discharge_kw" in dispatch.columns else 0.0
    )
    ev_v2g_revenue = 0.0
    if total_ev_discharge > 0.0 and "ev_discharge_kw" in dispatch.columns:
        ev_v2g_revenue = float((dispatch["ev_discharge_kw"] * tariff_arrays.csell).sum())

    return {
        "total_load_served": total_load_served,
        "total_unmet_load": total_unmet_load,
        "lpsp": lpsp,
        "total_pv_generation": total_pv_generation,
        "total_wt_generation": total_wt_generation,
        "total_dg_generation": total_dg_generation,
        "total_grid_bought": total_grid_bought,
        "total_grid_sold": total_grid_sold,
        "total_energy_dump": total_energy_dump,
        "total_battery_charge": total_battery_charge,
        "total_battery_discharge": total_battery_discharge,
        "annual_ev_charge_kwh": total_ev_charge,
        "annual_ev_discharge_kwh": total_ev_discharge,
        "ev_v2g_revenue": ev_v2g_revenue,
    }


def _heat_pump_statistics(dispatch: pd.DataFrame, comps: Any) -> dict[str, float | str]:
    """Return heat-pump production/input/COP metrics."""
    hp_elec_h = (
        dispatch["hp_elec_heating_kw"].to_numpy()
        if "hp_elec_heating_kw" in dispatch.columns
        else np.zeros(len(dispatch))
    )
    hp_elec_c = (
        dispatch["hp_elec_cooling_kw"].to_numpy()
        if "hp_elec_cooling_kw" in dispatch.columns
        else np.zeros(len(dispatch))
    )
    hp_heat_out = (
        dispatch["hp_heating_kw"].to_numpy()
        if "hp_heating_kw" in dispatch.columns
        else np.zeros(len(dispatch))
    )
    hp_cool_out = (
        dispatch["hp_cooling_kw"].to_numpy()
        if "hp_cooling_kw" in dispatch.columns
        else np.zeros(len(dispatch))
    )
    annual_hp_elec_kwh = float((hp_elec_h + hp_elec_c).sum())
    annual_heat_produced_kwh = float(hp_heat_out.sum())
    annual_cool_produced_kwh = float(hp_cool_out.sum())

    mask_h = hp_elec_h > 0.0
    mean_cop_heating = (
        float((hp_heat_out[mask_h] / hp_elec_h[mask_h]).mean()) if mask_h.any() else 0.0
    )
    mask_c = hp_elec_c > 0.0
    mean_cop_cooling = (
        float((hp_cool_out[mask_c] / hp_elec_c[mask_c]).mean()) if mask_c.any() else 0.0
    )

    hp_cfg = comps.heat_pump
    hp_model_name = hp_cfg.model_name or "" if hp_cfg is not None else ""
    return {
        "hp_model_name": hp_model_name,
        "annual_hp_elec_kwh": annual_hp_elec_kwh,
        "annual_heat_produced_kwh": annual_heat_produced_kwh,
        "annual_cool_produced_kwh": annual_cool_produced_kwh,
        "mean_cop_heating": mean_cop_heating,
        "mean_cop_cooling": mean_cop_cooling,
    }


def _thermal_storage_statistics(
    dispatch: pd.DataFrame,
    caps: dict[str, float],
    comps: Any,
) -> dict[str, float]:
    """Return thermal storage sizing/cycle/capex metrics."""
    ts_heat_kwh_th = float(caps.get("thermal_storage_heating_kwh_th", 0.0))
    ts_cool_kwh_th = float(caps.get("thermal_storage_cooling_kwh_th", 0.0))
    ts_cfg = comps.thermal_storage
    ts_h_charge = (
        dispatch["thermal_storage_heating_charge_kw"].to_numpy()
        if "thermal_storage_heating_charge_kw" in dispatch.columns
        else np.zeros(len(dispatch))
    )
    annual_thermal_storage_cycles = (
        float(ts_h_charge.sum()) / ts_heat_kwh_th if ts_heat_kwh_th > 0 else 0.0
    )
    ts_capex_per_kwh = ts_cfg.capex_per_kwh_th if ts_cfg is not None else 0.0
    thermal_storage_capex = (ts_heat_kwh_th + ts_cool_kwh_th) * ts_capex_per_kwh
    return {
        "thermal_storage_heating_kwh_th": ts_heat_kwh_th,
        "thermal_storage_cooling_kwh_th": ts_cool_kwh_th,
        "annual_thermal_storage_cycles": annual_thermal_storage_cycles,
        "thermal_storage_capex": thermal_storage_capex,
    }


def _thermal_load_statistics(dispatch: pd.DataFrame) -> dict[str, float]:
    """Return annual thermal demands and thermal LPSP metrics."""
    heat_demand_arr = (
        dispatch["heat_load_kw"].to_numpy()
        if "heat_load_kw" in dispatch.columns
        else np.zeros(len(dispatch))
    )
    heat_unmet_arr = (
        dispatch["heat_unmet_kw"].to_numpy()
        if "heat_unmet_kw" in dispatch.columns
        else np.zeros(len(dispatch))
    )
    cool_demand_arr = (
        dispatch["cool_load_kw"].to_numpy()
        if "cool_load_kw" in dispatch.columns
        else np.zeros(len(dispatch))
    )
    cool_unmet_arr = (
        dispatch["cool_unmet_kw"].to_numpy()
        if "cool_unmet_kw" in dispatch.columns
        else np.zeros(len(dispatch))
    )
    annual_heating_demand_kwh_th = float(heat_demand_arr.sum())
    annual_cooling_demand_kwh_th = float(cool_demand_arr.sum())
    total_heat_req = annual_heating_demand_kwh_th + float(heat_unmet_arr.sum())
    total_cool_req = annual_cooling_demand_kwh_th + float(cool_unmet_arr.sum())
    thermal_lpsp_heating = (
        float(heat_unmet_arr.sum()) / total_heat_req if total_heat_req > 0 else 0.0
    )
    thermal_lpsp_cooling = (
        float(cool_unmet_arr.sum()) / total_cool_req if total_cool_req > 0 else 0.0
    )
    return {
        "annual_heating_demand_kwh_th": annual_heating_demand_kwh_th,
        "annual_cooling_demand_kwh_th": annual_cooling_demand_kwh_th,
        "thermal_lpsp_heating": thermal_lpsp_heating,
        "thermal_lpsp_cooling": thermal_lpsp_cooling,
    }


def _diesel_and_emissions_statistics(
    dispatch: pd.DataFrame,
    comps: Any,
    total_grid_bought: float,
    total_load_served: float,
) -> dict[str, float | int]:
    """Return DG fuel/hours and emissions metrics."""
    dg_kw = _attr(comps, "diesel_generator", "capacity_kw", 0.0)
    dg_gen_kwh: np.ndarray = dispatch["dg_gen"].values

    if dg_kw > 0 and dg_gen_kwh.sum() > 0:
        slope = _attr(comps, "diesel_generator", "slope_l_per_kwh", 0.246)
        intercept = _attr(comps, "diesel_generator", "intercept_l_per_kw_hr", 0.084)
        fuel_l = dg_fuel_liters(dg_gen_kwh, dg_kw, slope, intercept)
        dg_op_hours = int(np.count_nonzero(dg_gen_kwh > 0.01))
    else:
        fuel_l = 0.0
        dg_op_hours = 0

    dg_co2_factor = _attr(comps, "diesel_generator", "co2_per_liter_kg", DEFAULT_DG_EMISSION_FACTOR)
    grid_co2_factor = _attr(
        comps, "grid", "emission_factor_kg_per_kwh", DEFAULT_GRID_EMISSION_FACTOR
    )
    dg_emis_kg = dg_emissions_kg(fuel_l, dg_co2_factor)
    grid_emis_kg = grid_emissions_kg(total_grid_bought, grid_co2_factor)
    total_emis_kg = dg_emis_kg + grid_emis_kg
    lem = total_emis_kg / total_load_served if total_load_served > 0.0 else 0.0
    return {
        "dg_operating_hours": dg_op_hours,
        "dg_fuel_consumption_liters": fuel_l,
        "dg_emissions_kg": dg_emis_kg,
        "grid_emissions_kg": grid_emis_kg,
        "total_emissions_kg": total_emis_kg,
        "lem": lem,
    }


def _monthly_grid_statistics(
    dispatch: pd.DataFrame,
    tariff_arrays: TariffArrays,
) -> tuple[list[float], list[float]]:
    """Return monthly grid import kWh and cost lists."""
    days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    grid_buy_arr: np.ndarray = dispatch["grid_buy"].to_numpy()
    cbuy_arr: np.ndarray = tariff_arrays.cbuy
    monthly_grid_kwh: list[float] = []
    monthly_grid_cost: list[float] = []
    hour = 0
    for days in days_per_month:
        hour_end = hour + days * 24
        month_kwh = float(grid_buy_arr[hour:hour_end].sum())
        month_cost = float((grid_buy_arr[hour:hour_end] * cbuy_arr[hour:hour_end]).sum())
        monthly_grid_kwh.append(round(month_kwh, 4))
        monthly_grid_cost.append(round(month_cost, 4))
        hour = hour_end
    return monthly_grid_kwh, monthly_grid_cost


def compute_kpis(
    scenario: Scenario,
    dispatch_result: DispatchResult,
    tariff_arrays: TariffArrays,
) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
    """Compute all KPIs, economics breakdown, and sizing table.

    Parameters
    ----------
    scenario:
        Validated :class:'~samba.scenario.models.Scenario'.
    dispatch_result:
        :class:'~samba.solver.extract.DispatchResult' from the solver.
    tariff_arrays:
        :class:'~samba.tariff.resolver.TariffArrays' for the scenario.

    Returns
    -------
    tuple[dict, dict, pd.DataFrame]
        ''(kpis, economics, sizing)'' where:

        * *kpis* -- dict matching ''kpis.json'' schema (28 fields).
        * *economics* -- dict matching ''economics.json'' schema.
        * *sizing* -- DataFrame with columns ''component'', ''capacity'',
          ''unit'', ''count'', ''capital_cost''.
    """
    economics = build_economics(scenario, dispatch_result, tariff_arrays)

    dispatch = dispatch_result.dispatch
    caps = dispatch_result.capacities
    comps = scenario.components
    project = scenario.project

    n = project.lifetime_years
    r_real = real_discount_rate(project.discount_rate_nominal, project.inflation_rate)
    crf_val = _crf(r_real, n)

    energy_stats = _energy_statistics(dispatch, tariff_arrays)
    hp_stats = _heat_pump_statistics(dispatch, comps)
    thermal_storage_stats = _thermal_storage_statistics(dispatch, caps, comps)
    thermal_load_stats = _thermal_load_statistics(dispatch)

    total_load_served = float(energy_stats["total_load_served"])
    total_unmet_load = float(energy_stats["total_unmet_load"])
    lpsp = float(energy_stats["lpsp"])
    total_pv_generation = float(energy_stats["total_pv_generation"])
    total_wt_generation = float(energy_stats["total_wt_generation"])
    total_dg_generation = float(energy_stats["total_dg_generation"])
    total_grid_bought = float(energy_stats["total_grid_bought"])
    total_grid_sold = float(energy_stats["total_grid_sold"])
    total_energy_dump = float(energy_stats["total_energy_dump"])
    total_battery_charge = float(energy_stats["total_battery_charge"])
    total_battery_discharge = float(energy_stats["total_battery_discharge"])
    total_ev_charge = float(energy_stats["annual_ev_charge_kwh"])
    total_ev_discharge = float(energy_stats["annual_ev_discharge_kwh"])
    ev_v2g_revenue = float(energy_stats["ev_v2g_revenue"])

    hp_model_name = str(hp_stats["hp_model_name"])
    annual_hp_elec_kwh = float(hp_stats["annual_hp_elec_kwh"])
    annual_heat_produced_kwh = float(hp_stats["annual_heat_produced_kwh"])
    annual_cool_produced_kwh = float(hp_stats["annual_cool_produced_kwh"])
    mean_cop_heating = float(hp_stats["mean_cop_heating"])
    mean_cop_cooling = float(hp_stats["mean_cop_cooling"])

    ts_heat_kwh_th = float(thermal_storage_stats["thermal_storage_heating_kwh_th"])
    ts_cool_kwh_th = float(thermal_storage_stats["thermal_storage_cooling_kwh_th"])
    annual_thermal_storage_cycles = float(thermal_storage_stats["annual_thermal_storage_cycles"])
    thermal_storage_capex = float(thermal_storage_stats["thermal_storage_capex"])

    annual_heating_demand_kwh_th = float(thermal_load_stats["annual_heating_demand_kwh_th"])
    annual_cooling_demand_kwh_th = float(thermal_load_stats["annual_cooling_demand_kwh_th"])
    thermal_lpsp_heating = float(thermal_load_stats["thermal_lpsp_heating"])
    thermal_lpsp_cooling = float(thermal_load_stats["thermal_lpsp_cooling"])

    # RE = (Ppv + Pwt) x eta_inv / total_AC.
    # pv_gen and wt_gen are DC-side flows; dg_gen and grid_bought are AC-side.
    # Multiplying by eta_inv places all terms on a consistent AC-energy basis.
    # comps.inverter is always present (required field in Components).
    eta_inv: float = comps.inverter.efficiency
    renewable_generation_ac = (total_pv_generation + total_wt_generation) * eta_inv
    total_generation = renewable_generation_ac + total_dg_generation + total_grid_bought
    renewable_fraction = (
        renewable_generation_ac / total_generation if total_generation > 0.0 else 0.0
    )

    dg_emissions_stats = _diesel_and_emissions_statistics(
        dispatch=dispatch,
        comps=comps,
        total_grid_bought=total_grid_bought,
        total_load_served=total_load_served,
    )
    dg_op_hours = int(dg_emissions_stats["dg_operating_hours"])
    fuel_l = float(dg_emissions_stats["dg_fuel_consumption_liters"])
    dg_emis_kg = float(dg_emissions_stats["dg_emissions_kg"])
    grid_emis_kg = float(dg_emissions_stats["grid_emissions_kg"])
    total_emis_kg = float(dg_emissions_stats["total_emissions_kg"])
    lem = float(dg_emissions_stats["lem"])

    # ------------------------------------------------------------------
    # Financial KPIs derived from economics dict
    # ------------------------------------------------------------------
    npc = economics["npc"]
    initial_investment = economics["investment"]["total"]
    total_replacement_cost = sum(v["npv"] for v in economics["replacement_schedule"].values())
    total_om_cost = economics["om_annual_npv"]["total"]
    total_fuel_cost = economics["fuel"]["total_npv"]
    total_salvage = economics["salvage"]["total"]
    total_grid_cost_net = economics["grid"]["total_net_npv"]

    # Gas supply financial KPIs (Phase 23)
    _gas_econ = economics.get("gas", {})
    gs = comps.gas_supply
    _gs_on = gs is not None and bool(getattr(gs, "enabled", False))
    annual_gas_kwh_th = float(_gas_econ.get("annual_consumption_kwh_th", 0.0))
    annual_gas_cost_usd = float(_gas_econ.get("annual_cost_usd", 0.0))
    _gas_co2 = gs.co2_per_kwh_th if _gs_on and gs is not None else 0.205
    annual_gas_co2_kg = annual_gas_kwh_th * _gas_co2
    gas_boiler_capex = float(_gas_econ.get("capex", 0.0))
    gas_boiler_npc = (
        gas_boiler_capex
        + float(_gas_econ.get("fuel_npv", 0.0))
        + float(_gas_econ.get("service_npv", 0.0))
        + (economics["replacement_schedule"].get("gas_boiler", {}).get("npv", 0.0))
        + float(economics["om_annual_npv"].get("gas_boiler", 0.0))
        - float(economics["salvage"].get("gas_boiler", 0.0))
    )

    # LCOE: annualised NPC / annual load served
    annual_cost = npc * crf_val  # $/yr
    lcoe = annual_cost / total_load_served if total_load_served > 0.0 else 0.0

    # Operating cost: annualised non-capital costs
    operating_cost = (total_om_cost + total_fuel_cost + total_grid_cost_net) * crf_val

    monthly_grid_kwh, monthly_grid_cost = _monthly_grid_statistics(dispatch, tariff_arrays)

    # Demand-charge / NEM KPIs (v4); zero/identity when not configured
    from samba.tariff.demand import monthly_peak_import

    grid_econ = economics["grid"]
    annual_demand_charge_usd = float(grid_econ.get("annual_demand_charge_yr1", 0.0))
    annual_energy_net_usd = float(grid_econ.get("annual_energy_net_yr1", 0.0))
    peak_demand_kw_by_month = [
        round(float(x), 4) for x in monthly_peak_import(dispatch["grid_buy"].to_numpy())
    ]

    # Battery degradation KPIs (v4)
    from samba.batteries.degradation import annual_equivalent_full_cycles

    _batt = comps.battery
    _batt_kwh = caps.get("battery_kwh") or (
        _batt.capacity_kwh if _batt is not None and _batt.capacity_kwh else 0.0
    )
    annual_throughput_cycles = (
        annual_equivalent_full_cycles(total_battery_discharge, _batt_kwh) if _batt_kwh else 0.0
    )
    _batt_repl = economics["replacement_schedule"].get("battery", {})
    battery_eol_year = int(_batt_repl.get("lifetime_years", 0))

    # ------------------------------------------------------------------
    # KPI dict (all 28 required fields + 2 monthly breakdowns)
    # ------------------------------------------------------------------
    kpis: dict[str, Any] = {
        "kpi_contract_version": KPI_CONTRACT_VERSION,
        "npc": round(npc, 4),
        "lcoe": round(lcoe, 6),
        "operating_cost": round(operating_cost, 4),
        "initial_investment": round(initial_investment, 4),
        "total_replacement_cost": round(total_replacement_cost, 4),
        "total_om_cost": round(total_om_cost, 4),
        "total_fuel_cost": round(total_fuel_cost, 4),
        "total_salvage": round(total_salvage, 4),
        "total_grid_cost_net": round(total_grid_cost_net, 4),
        "crf": round(crf_val, 6),
        "total_load_served": round(total_load_served, 4),
        "total_unmet_load": round(total_unmet_load, 4),
        "lpsp": round(lpsp, 6),
        "renewable_fraction": round(renewable_fraction, 6),
        "total_pv_generation": round(total_pv_generation, 4),
        "total_wt_generation": round(total_wt_generation, 4),
        "total_dg_generation": round(total_dg_generation, 4),
        "total_grid_bought": round(total_grid_bought, 4),
        "total_grid_sold": round(total_grid_sold, 4),
        "annual_demand_charge_usd": round(annual_demand_charge_usd, 4),
        "annual_energy_net_usd": round(annual_energy_net_usd, 4),
        "total_energy_dump": round(total_energy_dump, 4),
        "total_battery_charge": round(total_battery_charge, 4),
        "total_battery_discharge": round(total_battery_discharge, 4),
        "annual_throughput_cycles": round(annual_throughput_cycles, 4),
        "battery_eol_year": battery_eol_year,
        "dg_emissions_kg": round(dg_emis_kg, 4),
        "grid_emissions_kg": round(grid_emis_kg, 4),
        "total_emissions_kg": round(total_emis_kg, 4),
        "lem": round(lem, 6),
        "dg_operating_hours": dg_op_hours,
        "dg_fuel_consumption_liters": round(fuel_l, 4),
        "annual_ev_charge_kwh": round(total_ev_charge, 4),
        "annual_ev_discharge_kwh": round(total_ev_discharge, 4),
        "ev_v2g_revenue": round(ev_v2g_revenue, 4),
        "monthly_grid_kwh": monthly_grid_kwh,
        "monthly_grid_cost": monthly_grid_cost,
        "peak_demand_kw_by_month": peak_demand_kw_by_month,
        # Heat pump KPIs (zero / empty when no HP is modeled)
        "hp_model_name": hp_model_name,
        "annual_hp_elec_kwh": round(annual_hp_elec_kwh, 4),
        "annual_heat_produced_kwh": round(annual_heat_produced_kwh, 4),
        "annual_cool_produced_kwh": round(annual_cool_produced_kwh, 4),
        "mean_cop_heating": round(mean_cop_heating, 4),
        "mean_cop_cooling": round(mean_cop_cooling, 4),
        # Thermal storage KPIs (zero when no thermal storage modeled)
        "thermal_storage_heating_kwh_th": round(ts_heat_kwh_th, 4),
        "thermal_storage_cooling_kwh_th": round(ts_cool_kwh_th, 4),
        "annual_thermal_storage_cycles": round(annual_thermal_storage_cycles, 4),
        "thermal_storage_capex": round(thermal_storage_capex, 2),
        # Thermal load KPIs (Phase 22 -- zero when no thermal load is modeled)
        "annual_heating_demand_kwh_th": round(annual_heating_demand_kwh_th, 4),
        "annual_cooling_demand_kwh_th": round(annual_cooling_demand_kwh_th, 4),
        "thermal_lpsp_heating": round(thermal_lpsp_heating, 6),
        "thermal_lpsp_cooling": round(thermal_lpsp_cooling, 6),
        # Gas supply KPIs (Phase 23 -- zero when no gas supply modeled)
        "annual_gas_consumption_kwh_th": round(annual_gas_kwh_th, 4),
        "annual_gas_cost_usd": round(annual_gas_cost_usd, 4),
        "annual_gas_co2_kg": round(annual_gas_co2_kg, 4),
        "gas_boiler_capex": round(gas_boiler_capex, 4),
        "gas_boiler_npc": round(gas_boiler_npc, 4),
    }

    # ------------------------------------------------------------------
    # Sizing table
    # ------------------------------------------------------------------
    sizing = _build_sizing(scenario, caps, economics)

    return kpis, economics, sizing


# ---------------------------------------------------------------------------
# Sizing table builder
# ---------------------------------------------------------------------------


def _build_sizing(
    scenario: Scenario, caps: dict[str, float], economics: dict[str, Any]
) -> pd.DataFrame:
    """Return a DataFrame matching the ''sizing.csv'' schema.

    Columns: ''component'', ''capacity'', ''unit'', ''count'',
    ''capital_cost''.
    """
    comps = scenario.components
    rows = []

    def _row(
        component: str,
        capacity: float,
        unit: str,
        count: int,
        capital_cost: float,
    ) -> None:
        if capacity > 0 or capital_cost > 0:
            rows.append(
                {
                    "component": component,
                    "capacity": round(capacity, 4),
                    "unit": unit,
                    "count": count,
                    "capital_cost": round(capital_cost, 4),
                }
            )

    pv_kw = _get_pv_kw(comps, caps)
    pv_capex = economics["investment"]["pv"]
    _row("pv", pv_kw, "kW", 1, pv_capex)

    battery_kwh = _get_battery_kwh(comps, caps)
    battery_kw = caps.get("battery_kw", 0.0)
    battery_capex = economics["investment"]["battery"]
    _row("battery_energy", battery_kwh, "kWh", 1, battery_capex)
    if battery_kw > 0:
        _row("battery_power", battery_kw, "kW", 1, 0.0)

    inverter_kw = _get_inverter_kw(comps, caps)
    inv_capex = economics["investment"]["inverter"]
    _row("inverter", inverter_kw, "kW", 1, inv_capex)

    wt_count = getattr(getattr(comps, "wind_turbine", None), "count", 0) or 0
    wt_kw = caps.get("wt_kw", 0.0)
    wt_kw_per_unit = wt_kw / wt_count if wt_count > 0 and wt_kw > 0 else 0.0
    wt_capex = economics["investment"]["wind_turbine"]
    _row("wind_turbine", wt_kw_per_unit, "kW", wt_count, wt_capex)

    dg_kw = _attr(comps, "diesel_generator", "capacity_kw", 0.0)
    dg_capex = economics["investment"]["diesel_generator"]
    _row("diesel_generator", dg_kw, "kW", 1, dg_capex)

    grid_capex = _attr(comps, "grid", "capex", 0.0)
    _row("grid", 0.0, "-", 1, grid_capex)

    return pd.DataFrame(rows, columns=["component", "capacity", "unit", "count", "capital_cost"])
