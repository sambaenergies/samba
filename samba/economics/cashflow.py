# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Central economics orchestrator: investment, O&M, fuel, grid, replacement, salvage.

This module takes a solved :class:'~samba.solver.extract.DispatchResult' and
produces the ''economics'' dict that is written to ''economics.json'' (schema
in ''docs/developer/results-contract.md'').

Usage::

    from samba.economics.cashflow import build_economics

    economics_dict = build_economics(scenario, dispatch_result, tariff_arrays)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from samba.compiler.annualize import crf
from samba.economics.npc import (
    escalated_present_worth_factor,
    present_worth_factor,
    real_discount_rate,
)
from samba.economics.replacement import replacement_npv, replacement_years
from samba.economics.salvage import salvage_npv
from samba.tariff.demand import annual_demand_charge, nem_annual_grid_cost

if TYPE_CHECKING:
    import pandas as pd

    from samba.scenario.models import Scenario
    from samba.solver.extract import DispatchResult
    from samba.tariff.resolver import TariffArrays

__all__ = ["build_economics"]


@dataclass
class _GasCostBreakdown:
    """Gas fuel/service annual and NPV costs."""

    annual_kwh_th: float
    annual_cost: float
    fuel_npv: float
    service_npv: float


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_economics(
    scenario: Scenario,
    dispatch_result: DispatchResult,
    tariff_arrays: TariffArrays,
) -> dict[str, Any]:
    """Compute the full economics dictionary.

    Produces the schema described in ''docs/developer/results-contract.md
    Sec.economics.json''.

    Parameters
    ----------
    scenario:
        Validated :class:'~samba.scenario.models.Scenario'.
    dispatch_result:
        :class:'~samba.solver.extract.DispatchResult' from the solver.
    tariff_arrays:
        :class:'~samba.tariff.resolver.TariffArrays' (buy / sell price arrays
        and service charges).

    Returns
    -------
    dict
        ''economics.json''-compatible dictionary.
    """
    project = scenario.project
    comps = scenario.components
    caps = dispatch_result.capacities  # e.g. {"pv_kw": 50.0, "battery_kwh": 100.0, ...}
    dispatch = dispatch_result.dispatch

    n: int = project.lifetime_years
    r_nom: float = project.discount_rate_nominal
    r_inf: float = project.inflation_rate
    r_real: float = real_discount_rate(r_nom, r_inf)
    pwf: float = present_worth_factor(r_real, n)
    crf_val: float = crf(r_real, n)

    # ------------------------------------------------------------------
    # Effective capacities (investment mode -> from solver; fixed -> from model)
    # ------------------------------------------------------------------
    pv_kw = _get_pv_kw(comps, caps)
    battery_kwh = _get_battery_kwh(comps, caps)
    inverter_kw = _get_inverter_kw(comps, caps)
    wt_count = getattr(getattr(comps, "wind_turbine", None), "count", 1)
    wt_kw = caps.get("wt_kw", 0.0)  # total WT capacity
    dg_kw = getattr(getattr(comps, "diesel_generator", None), "capacity_kw", 0.0) or 0.0

    # ------------------------------------------------------------------
    # Capex per component (total, in today's dollars)
    # ------------------------------------------------------------------
    pv_capex = pv_kw * _attr(comps, "pv", "capex_per_kw", 0.0)
    battery_capex = battery_kwh * _attr(comps, "battery", "capex_per_kwh", 0.0)
    inverter_capex = inverter_kw * _attr(comps, "inverter", "capex_per_kw", 0.0)
    wt_capex = wt_count * _attr(comps, "wind_turbine", "capex_per_unit", 0.0)
    dg_capex = dg_kw * _attr(comps, "diesel_generator", "capex_per_kw", 0.0)
    grid_capex = _attr(comps, "grid", "capex", 0.0)

    # Gas supply (Phase 23) -- scalar capex/O&M, fuel NPV computed later.
    gs = comps.gas_supply
    _gs_on = gs is not None and bool(gs.enabled)
    gas_capex = float(gs.capex) if gs is not None and gs.enabled else 0.0
    gas_om_yr = float(gs.opex_per_year) if gs is not None and gs.enabled else 0.0

    # RE incentive deduction (applied to PV + battery, positive = reduction to owner)
    re_rate: float = project.re_incentive_rate
    re_incentive_applied = -re_rate * (pv_capex + battery_capex)  # negative value (reduces cost)

    engineering = 0.0  # v1: no engineering fee in scenario schema

    total_investment = (
        pv_capex
        + battery_capex
        + inverter_capex
        + wt_capex
        + dg_capex
        + grid_capex
        + gas_capex
        + engineering
        + re_incentive_applied  # negative
    )

    investment_breakdown = {
        "pv": round(pv_capex, 4),
        "wind_turbine": round(wt_capex, 4),
        "battery": round(battery_capex, 4),
        "diesel_generator": round(dg_capex, 4),
        "inverter": round(inverter_capex, 4),
        "charger": 0.0,
        "gas_boiler": round(gas_capex, 4),
        "engineering": round(engineering, 4),
        "nem_fee": 0.0,
        "re_incentive_applied": round(re_incentive_applied, 4),
        "total": round(total_investment, 4),
    }

    # Battery degradation (v4): derive an effective lifetime from solved throughput.
    battery_lifetime_override: float | None = None
    battery_nameplate_life = _attr(comps, "battery", "lifetime_years", 10)
    batt_degradation = getattr(comps.battery, "degradation", None) if comps.battery else None
    annual_battery_discharge = (
        float(dispatch["batt_discharge"].sum()) if "batt_discharge" in dispatch else 0.0
    )
    if batt_degradation is not None and battery_kwh > 0:
        from samba.batteries.degradation import effective_battery_lifetime_years

        battery_lifetime_override = effective_battery_lifetime_years(
            batt_degradation,
            annual_battery_discharge,
            battery_kwh,
            battery_nameplate_life,
        )

    battery_life_for_schedule = (
        battery_lifetime_override
        if battery_lifetime_override is not None
        else battery_nameplate_life
    )

    replacement_schedule, total_replacement_npv = _build_replacement_schedule(
        n=n,
        r_real=r_real,
        comps=comps,
        pv_kw=pv_kw,
        pv_capex=pv_capex,
        battery_kwh=battery_kwh,
        battery_capex=battery_capex,
        inverter_kw=inverter_kw,
        inverter_capex=inverter_capex,
        wt_kw=wt_kw,
        wt_capex=wt_capex,
        dg_kw=dg_kw,
        dg_capex=dg_capex,
        gas_capex=gas_capex,
        gas_supply=gs,
        battery_lifetime_override=battery_lifetime_override,
    )

    # ------------------------------------------------------------------
    # Annual O&M costs -> NPV over project lifetime
    # ------------------------------------------------------------------
    om_annual_npv, total_om_yr, total_om_npv = _build_om_breakdown(
        comps=comps,
        pv_kw=pv_kw,
        battery_kwh=battery_kwh,
        inverter_kw=inverter_kw,
        wt_count=wt_count,
        dg_kw=dg_kw,
        gas_om_yr=gas_om_yr,
        pwf=pwf,
    )

    # ------------------------------------------------------------------
    # Diesel fuel cost
    # ------------------------------------------------------------------
    dg_gen_kwh: np.ndarray = dispatch["dg_gen"].values
    fuel_annual_liters, fuel_annual_cost = _fuel_cost(scenario, comps, dg_gen_kwh, dg_kw)
    fuel_total_npv = fuel_annual_cost * pwf

    fuel_breakdown = {
        "annual_consumption_liters": round(fuel_annual_liters, 4),
        "total_npv": round(fuel_total_npv, 4),
    }

    gas_costs = _compute_gas_costs(gas_supply=gs, dispatch=dispatch, pwf=pwf)
    annual_gas_kwh_th = gas_costs.annual_kwh_th
    annual_gas_cost = gas_costs.annual_cost
    gas_fuel_npv = gas_costs.fuel_npv
    gas_service_npv = gas_costs.service_npv

    salvage_breakdown, total_salvage_npv = _build_salvage_breakdown(
        n=n,
        r_real=r_real,
        comps=comps,
        pv_capex=pv_capex,
        battery_capex=battery_capex,
        inverter_capex=inverter_capex,
        wt_capex=wt_capex,
        dg_capex=dg_capex,
        gas_capex=gas_capex,
        gas_supply=gs,
        battery_lifetime_override=battery_lifetime_override,
    )

    # ------------------------------------------------------------------
    # Grid costs
    # ------------------------------------------------------------------
    grid_breakdown, grid_net_npv = _grid_costs(
        dispatch, tariff_arrays, pwf, r_real, n, project.grid_escalation_rate, scenario.tariff
    )

    # ------------------------------------------------------------------
    # NPC
    # ------------------------------------------------------------------
    npc = (
        total_investment
        + total_replacement_npv
        + total_om_npv
        + fuel_total_npv
        + gas_fuel_npv
        + gas_service_npv
        + grid_net_npv
        - total_salvage_npv
    )

    # ------------------------------------------------------------------
    # Annual cashflow table (year 0 ... n)
    # ------------------------------------------------------------------
    cashflow_annual = _build_cashflow_table(
        n=n,
        r_real=r_real,
        total_investment=total_investment,
        # per-component capex + lifetimes for replacement timing
        components_capex=[
            ("pv", pv_capex, _attr(comps, "pv", "lifetime_years", 25)),
            ("battery", battery_capex, battery_life_for_schedule),
            ("inverter", inverter_capex, _attr(comps, "inverter", "lifetime_years", 10)),
            ("wind_turbine", wt_capex, _attr(comps, "wind_turbine", "lifetime_years", 20)),
            ("diesel_generator", dg_capex, _attr(comps, "diesel_generator", "lifetime_years", 15)),
        ],
        om_annual=total_om_yr,
        fuel_annual=fuel_annual_cost,
        grid_annual=grid_breakdown["annual_energy_net_yr1"]
        + grid_breakdown["annual_service_charge"]
        + grid_breakdown["annual_demand_charge_yr1"],
        # salvage applies only in the last year (nominal, then discounted)
        salvage_components=[
            ("pv", pv_capex, _attr(comps, "pv", "lifetime_years", 25)),
            ("battery", battery_capex, battery_life_for_schedule),
            ("inverter", inverter_capex, _attr(comps, "inverter", "lifetime_years", 10)),
            ("wind_turbine", wt_capex, _attr(comps, "wind_turbine", "lifetime_years", 20)),
            ("diesel_generator", dg_capex, _attr(comps, "diesel_generator", "lifetime_years", 15)),
        ],
    )

    # ------------------------------------------------------------------
    # Assemble economics dict
    # ------------------------------------------------------------------
    economics: dict[str, Any] = {
        "discount_rate_real": round(r_real, 6),
        "project_lifetime_years": n,
        "crf": round(crf_val, 6),
        "npc": round(npc, 4),
        "investment": investment_breakdown,
        "replacement_schedule": replacement_schedule,
        "om_annual_npv": om_annual_npv,
        "fuel": fuel_breakdown,
        "salvage": salvage_breakdown,
        "grid": grid_breakdown,
        "gas": {
            "annual_consumption_kwh_th": round(annual_gas_kwh_th, 4),
            "annual_cost_usd": round(annual_gas_cost, 4),
            "fuel_npv": round(gas_fuel_npv, 4),
            "service_npv": round(gas_service_npv, 4),
            "capex": round(gas_capex, 4),
        },
        "cashflow_annual": cashflow_annual,
    }

    return economics


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_replacement_schedule(
    *,
    n: int,
    r_real: float,
    comps: Any,
    pv_kw: float,
    pv_capex: float,
    battery_kwh: float,
    battery_capex: float,
    inverter_kw: float,
    inverter_capex: float,
    wt_kw: float,
    wt_capex: float,
    dg_kw: float,
    dg_capex: float,
    gas_capex: float,
    gas_supply: Any | None,
    battery_lifetime_override: float | None = None,
) -> tuple[dict[str, Any], float]:
    """Build replacement schedule breakdown and total replacement NPV.

    ``battery_lifetime_override`` (v4) replaces the battery's nameplate lifetime
    when a degradation model derives a throughput-based effective lifetime.
    """
    schedule: dict[str, Any] = {}

    def _add(label: str, capex: float, component_lifetime: float) -> None:
        if capex <= 0 or component_lifetime <= 0:
            return
        lifetime_years = int(component_lifetime)
        years = replacement_years(n, lifetime_years)
        npv_val = replacement_npv(capex, n, lifetime_years, r_real)
        schedule[label] = {
            "lifetime_years": lifetime_years,
            "replacements": len(years),
            "npv": round(npv_val, 4),
        }

    if pv_kw > 0:
        _add("pv", pv_capex, _attr(comps, "pv", "lifetime_years", 25))
    if battery_kwh > 0:
        battery_life = (
            battery_lifetime_override
            if battery_lifetime_override is not None
            else _attr(comps, "battery", "lifetime_years", 10)
        )
        _add("battery", battery_capex, battery_life)
    if inverter_kw > 0:
        _add("inverter", inverter_capex, _attr(comps, "inverter", "lifetime_years", 10))
    if wt_kw > 0:
        _add("wind_turbine", wt_capex, _attr(comps, "wind_turbine", "lifetime_years", 20))
    if dg_kw > 0:
        _add("diesel_generator", dg_capex, _attr(comps, "diesel_generator", "lifetime_years", 15))
    if gas_capex > 0 and gas_supply is not None and bool(getattr(gas_supply, "enabled", False)):
        _add("gas_boiler", gas_capex, float(getattr(gas_supply, "lifetime_years", 20)))

    total_replacement_npv = sum(item["npv"] for item in schedule.values())
    return schedule, total_replacement_npv


def _build_om_breakdown(
    *,
    comps: Any,
    pv_kw: float,
    battery_kwh: float,
    inverter_kw: float,
    wt_count: float,
    dg_kw: float,
    gas_om_yr: float,
    pwf: float,
) -> tuple[dict[str, float], float, float]:
    """Build annual O&M NPV breakdown and totals."""
    pv_om_yr = pv_kw * _attr(comps, "pv", "opex_per_kw_yr", 0.0)
    battery_om_yr = battery_kwh * _attr(comps, "battery", "opex_per_kwh_yr", 0.0)
    inverter_om_yr = inverter_kw * _attr(comps, "inverter", "opex_per_kw_yr", 0.0)
    wt_om_yr = wt_count * _attr(comps, "wind_turbine", "opex_per_unit_yr", 0.0)
    dg_om_yr = dg_kw * _attr(comps, "diesel_generator", "opex_per_kw_yr", 0.0)
    grid_om_yr = _attr(comps, "grid", "opex_yr", 0.0)

    total_om_yr = (
        pv_om_yr + battery_om_yr + inverter_om_yr + wt_om_yr + dg_om_yr + grid_om_yr + gas_om_yr
    )
    total_om_npv = total_om_yr * pwf
    breakdown = {
        "pv": round(pv_om_yr * pwf, 4),
        "battery": round(battery_om_yr * pwf, 4),
        "inverter": round(inverter_om_yr * pwf, 4),
        "wind_turbine": round(wt_om_yr * pwf, 4),
        "diesel_generator": round(dg_om_yr * pwf, 4),
        "grid": round(grid_om_yr * pwf, 4),
        "gas_boiler": round(gas_om_yr * pwf, 4),
        "total": round(total_om_npv, 4),
    }
    return breakdown, total_om_yr, total_om_npv


def _compute_gas_costs(
    *,
    gas_supply: Any | None,
    dispatch: pd.DataFrame,
    pwf: float,
) -> _GasCostBreakdown:
    """Compute gas annual and NPV costs."""
    if gas_supply is None or not bool(getattr(gas_supply, "enabled", False)):
        return _GasCostBreakdown(0.0, 0.0, 0.0, 0.0)

    from samba.tariff.gas import build_gas_rate_array

    gas_rate_array = build_gas_rate_array(gas_supply.tariff)
    if "gas_boiler_input_kw_th" in dispatch.columns:
        gas_input_kw_arr: np.ndarray = dispatch["gas_boiler_input_kw_th"].to_numpy()
    else:
        gas_input_kw_arr = np.zeros(len(dispatch))

    annual_kwh_th = float(gas_input_kw_arr.sum())
    annual_unit_cost = float((gas_input_kw_arr * gas_rate_array).sum())
    service_per_year = float(getattr(gas_supply.tariff, "monthly_service_charge", 0.0)) * 12
    annual_cost = annual_unit_cost + service_per_year
    return _GasCostBreakdown(
        annual_kwh_th=annual_kwh_th,
        annual_cost=annual_cost,
        fuel_npv=annual_unit_cost * pwf,
        service_npv=service_per_year * pwf,
    )


def _salvage_npv_safe(capex: float, component_lifetime: float, n: int, r_real: float) -> float:
    """Return salvage NPV for a component, guarded for zero/invalid inputs."""
    if capex <= 0 or component_lifetime <= 0:
        return 0.0
    return salvage_npv(capex, n, int(component_lifetime), r_real)


def _build_salvage_breakdown(
    *,
    n: int,
    r_real: float,
    comps: Any,
    pv_capex: float,
    battery_capex: float,
    inverter_capex: float,
    wt_capex: float,
    dg_capex: float,
    gas_capex: float,
    gas_supply: Any | None,
    battery_lifetime_override: float | None = None,
) -> tuple[dict[str, float], float]:
    """Build salvage breakdown dict and total salvage NPV."""
    pv_salvage = _salvage_npv_safe(pv_capex, _attr(comps, "pv", "lifetime_years", 25), n, r_real)
    battery_life = (
        battery_lifetime_override
        if battery_lifetime_override is not None
        else _attr(comps, "battery", "lifetime_years", 10)
    )
    battery_salvage = _salvage_npv_safe(battery_capex, battery_life, n, r_real)
    inverter_salvage = _salvage_npv_safe(
        inverter_capex,
        _attr(comps, "inverter", "lifetime_years", 10),
        n,
        r_real,
    )
    wt_salvage = _salvage_npv_safe(
        wt_capex,
        _attr(comps, "wind_turbine", "lifetime_years", 20),
        n,
        r_real,
    )
    dg_salvage = _salvage_npv_safe(
        dg_capex,
        _attr(comps, "diesel_generator", "lifetime_years", 15),
        n,
        r_real,
    )
    gas_lifetime = (
        float(getattr(gas_supply, "lifetime_years", 20))
        if gas_supply is not None and bool(getattr(gas_supply, "enabled", False))
        else 0.0
    )
    gas_salvage = _salvage_npv_safe(gas_capex, gas_lifetime, n, r_real)
    total_salvage_npv = (
        pv_salvage + battery_salvage + inverter_salvage + wt_salvage + dg_salvage + gas_salvage
    )
    breakdown = {
        "pv": round(pv_salvage, 4),
        "battery": round(battery_salvage, 4),
        "inverter": round(inverter_salvage, 4),
        "wind_turbine": round(wt_salvage, 4),
        "diesel_generator": round(dg_salvage, 4),
        "gas_boiler": round(gas_salvage, 4),
        "total": round(total_salvage_npv, 4),
    }
    return breakdown, total_salvage_npv


def _attr(comps: object, comp_name: str, attr: str, default: float) -> float:
    """Safely get a numeric attribute from a component model, with default."""
    comp = getattr(comps, comp_name, None)
    if comp is None:
        return default
    val = getattr(comp, attr, default)
    if val is None:
        return default
    return float(val)


def _get_pv_kw(comps: object, caps: dict[str, float]) -> float:
    """Return effective PV capacity (kW)."""
    if "pv_kw" in caps:
        return caps["pv_kw"]
    pv = getattr(comps, "pv", None)
    if pv is None:
        return 0.0
    return float(getattr(pv, "capacity_kw", 0.0) or 0.0)


def _get_battery_kwh(comps: object, caps: dict[str, float]) -> float:
    """Return effective battery capacity (kWh)."""
    if "battery_kwh" in caps:
        return caps["battery_kwh"]
    batt = getattr(comps, "battery", None)
    if batt is None:
        return 0.0
    return float(getattr(batt, "capacity_kwh", 0.0) or 0.0)


def _get_inverter_kw(comps: object, caps: dict[str, float]) -> float:
    """Return effective inverter capacity (kW)."""
    if "inverter_kw" in caps:
        return caps["inverter_kw"]
    inv = getattr(comps, "inverter", None)
    if inv is None:
        return 0.0
    return float(getattr(inv, "capacity_kw", 0.0) or 0.0)


def _fuel_cost(
    scenario: object, comps: object, dg_gen_kwh: np.ndarray, dg_kw: float
) -> tuple[float, float]:
    """Return (annual_liters, annual_cost_usd) for DG fuel."""
    if dg_kw <= 0 or dg_gen_kwh.sum() == 0:
        return 0.0, 0.0
    dg = getattr(comps, "diesel_generator", None)
    if dg is None:
        return 0.0, 0.0

    slope = float(getattr(dg, "slope_l_per_kwh", 0.246))
    intercept = float(getattr(dg, "intercept_l_per_kw_hr", 0.084))
    price = float(getattr(dg, "fuel_price_per_l", 0.0))

    from samba.economics.emissions import dg_fuel_liters

    fuel_l = dg_fuel_liters(dg_gen_kwh, dg_kw, slope, intercept)
    return fuel_l, fuel_l * price


def _grid_costs(
    dispatch: pd.DataFrame,
    tariff_arrays: TariffArrays,
    pwf: float,
    r_real: float = 0.0,
    n: int = 0,
    grid_escalation_rate: float = 0.0,
    tariff: Any = None,
) -> tuple[dict[str, Any], float]:
    """Compute grid cost breakdown and total net NPV.

    When ``tariff.nem`` is set, energy cost uses monthly NEM reconciliation
    instead of the simple annual ``bought − sold`` netting. When
    ``tariff.demand_charge`` is set, a ``$/kW-month`` charge on the monthly
    peak import is added (v4).
    """
    grid_buy: np.ndarray = dispatch["grid_buy"].values
    grid_sell: np.ndarray = dispatch["grid_sell"].values

    cbuy: np.ndarray = np.asarray(tariff_arrays.cbuy)
    csell: np.ndarray = np.asarray(tariff_arrays.csell)
    service_charges: np.ndarray = np.asarray(tariff_arrays.service_charge)

    annual_bought_cost = float(np.dot(grid_buy, cbuy))
    annual_sold_revenue = float(np.dot(grid_sell, csell))
    annual_service_charge = float(service_charges.sum())

    nem = getattr(tariff, "nem", None) if tariff is not None else None
    if nem is not None:
        annual_energy_net = nem_annual_grid_cost(
            grid_buy,
            grid_sell,
            cbuy,
            csell,
            carryover=nem.carryover,
            annual_excess_credit_fraction=nem.annual_excess_credit_fraction,
        )
    else:
        annual_energy_net = annual_bought_cost - annual_sold_revenue

    demand = getattr(tariff, "demand_charge", None) if tariff is not None else None
    if demand is not None:
        annual_demand = annual_demand_charge(grid_buy, demand.rate_per_kw_month, demand.hours)
    else:
        annual_demand = 0.0

    if grid_escalation_rate != 0.0 and n > 0:
        buy_pwf = escalated_present_worth_factor(r_real, grid_escalation_rate, n)
        sell_pwf = buy_pwf  # sell price tracks buy price escalation
        svc_pwf = pwf  # service charges use standard PWF (no escalation assumed)
    else:
        buy_pwf = pwf
        sell_pwf = pwf
        svc_pwf = pwf

    total_bought_npv = annual_bought_cost * buy_pwf
    total_sold_npv = annual_sold_revenue * sell_pwf
    total_demand_npv = annual_demand * buy_pwf
    total_net_npv = annual_energy_net * buy_pwf + annual_service_charge * svc_pwf + total_demand_npv

    breakdown = {
        "annual_bought_cost_yr1": round(annual_bought_cost, 4),
        "annual_sold_revenue_yr1": round(annual_sold_revenue, 4),
        "annual_service_charge": round(annual_service_charge, 4),
        "annual_energy_net_yr1": round(annual_energy_net, 4),
        "annual_demand_charge_yr1": round(annual_demand, 4),
        "total_bought_npv": round(total_bought_npv, 4),
        "total_sold_npv": round(total_sold_npv, 4),
        "total_demand_charge_npv": round(total_demand_npv, 4),
        "total_credits_npv": 0.0,
        "total_net_npv": round(total_net_npv, 4),
    }
    return breakdown, total_net_npv


def _build_cashflow_table(
    n: int,
    r_real: float,
    total_investment: float,
    components_capex: list[tuple[str, float, float]],
    om_annual: float,
    fuel_annual: float,
    grid_annual: float,
    salvage_components: list[tuple[str, float, float]],
) -> list[dict[str, Any]]:
    """Build the year-by-year cashflow table (undiscounted nominal values).

    Each row contains nominal (real) costs; the NPV columns in ''economics.json''
    use the discounted values already computed.  The cashflow table is provided
    for plotting / audit purposes using *real* (inflation-adjusted) annual values.

    Returns
    -------
    list[dict]
        One dict per year from 0 to ''n'' inclusive.
    """
    # Build replacement lookup: {year: total_replacement_cost}
    replacements_by_year: dict[int, float] = {}
    for _label, capex, lifetime in components_capex:
        if capex <= 0 or lifetime <= 0:
            continue
        for yr in replacement_years(n, int(lifetime)):
            replacements_by_year[yr] = replacements_by_year.get(yr, 0.0) + capex

    # Compute salvage total (nominal, at real value)
    from samba.economics.salvage import salvage_fraction

    total_salvage_nominal = 0.0
    for _label, capex, lifetime in salvage_components:
        if capex <= 0 or lifetime <= 0:
            continue
        frac = salvage_fraction(n, int(lifetime))
        total_salvage_nominal += capex * frac

    rows = []
    for yr in range(n + 1):
        investment = total_investment if yr == 0 else 0.0
        om = om_annual if yr > 0 else 0.0
        fuel = fuel_annual if yr > 0 else 0.0
        replacement = replacements_by_year.get(yr, 0.0)
        grid_net = grid_annual if yr > 0 else 0.0
        salvage = total_salvage_nominal if yr == n else 0.0
        total = investment + om + fuel + replacement + grid_net - salvage
        rows.append(
            {
                "year": yr,
                "investment": round(investment, 4),
                "om": round(om, 4),
                "fuel": round(fuel, 4),
                "replacement": round(replacement, 4),
                "grid_net": round(grid_net, 4),
                "salvage": round(salvage, 4),
                "total": round(total, 4),
            }
        )

    return rows
