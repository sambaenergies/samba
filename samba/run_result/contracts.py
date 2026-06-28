# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Pydantic contracts for the run-result artifacts (``kpis.json`` etc.).

These models are the **single source of truth** for the shapes the UI consumes.
They mirror the dicts/DataFrames produced by :mod:`samba.run_result.kpis` and
:mod:`samba.economics.cashflow`; JSON Schemas are generated from them
(``scripts/export_schemas.py``) and the UI generates its TypeScript types from
those schemas, so the two sides cannot silently drift.

The models are validated against live solver output by
``tests/unit/test_artifact_contracts.py``. If a KPI/economics/sizing field is
added or renamed, update the model here and regenerate the schemas
(``just schemas``) — the drift test will fail until both are in sync.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = [
    "KpiSummary",
    "CashflowYear",
    "EconomicsReport",
    "SizingRow",
    "DispatchContract",
]


class KpiSummary(BaseModel):
    """Mirrors ``kpis.json`` (the dict from :func:`samba.run_result.kpis.compute_kpis`).

    The key set is fixed: heat-pump / thermal / gas KPIs default to zero (or an
    empty string) when those components are not modelled, rather than being
    omitted. ``renewable_fraction``, ``lpsp``, and ``lem`` are fractions in
    ``[0, 1]`` (the UI renders the first two as percentages).
    """

    model_config = ConfigDict(extra="forbid")

    kpi_contract_version: str

    # Economics summary
    npc: float
    lcoe: float
    operating_cost: float
    initial_investment: float
    total_replacement_cost: float
    total_om_cost: float
    total_fuel_cost: float
    total_salvage: float
    total_grid_cost_net: float
    crf: float

    # Energy balance / reliability
    total_load_served: float
    total_unmet_load: float
    lpsp: float
    renewable_fraction: float
    total_pv_generation: float
    total_wt_generation: float
    total_dg_generation: float
    total_grid_bought: float
    total_grid_sold: float
    annual_demand_charge_usd: float
    annual_energy_net_usd: float
    total_energy_dump: float

    # Battery
    total_battery_charge: float
    total_battery_discharge: float
    annual_throughput_cycles: float
    battery_eol_year: int

    # Emissions
    dg_emissions_kg: float
    grid_emissions_kg: float
    total_emissions_kg: float
    lem: float

    # Diesel
    dg_operating_hours: int
    dg_fuel_consumption_liters: float

    # EV / V2G
    annual_ev_charge_kwh: float
    annual_ev_discharge_kwh: float
    ev_v2g_revenue: float

    # Monthly breakdowns
    monthly_grid_kwh: list[float]
    monthly_grid_cost: list[float]
    peak_demand_kw_by_month: list[float]

    # Heat pump (zero / empty when no HP modelled)
    hp_model_name: str
    annual_hp_elec_kwh: float
    annual_heat_produced_kwh: float
    annual_cool_produced_kwh: float
    mean_cop_heating: float
    mean_cop_cooling: float

    # Thermal storage (zero when none modelled)
    thermal_storage_heating_kwh_th: float
    thermal_storage_cooling_kwh_th: float
    annual_thermal_storage_cycles: float
    thermal_storage_capex: float

    # Thermal load (zero when none modelled)
    annual_heating_demand_kwh_th: float
    annual_cooling_demand_kwh_th: float
    thermal_lpsp_heating: float
    thermal_lpsp_cooling: float

    # Gas supply (zero when none modelled)
    annual_gas_consumption_kwh_th: float
    annual_gas_cost_usd: float
    annual_gas_co2_kg: float
    gas_boiler_capex: float
    gas_boiler_npc: float


class CashflowYear(BaseModel):
    """One row of ``economics.json`` ``cashflow_annual`` (per project year)."""

    model_config = ConfigDict(extra="forbid")

    year: int
    investment: float
    om: float
    fuel: float
    grid_net: float
    replacement: float
    salvage: float
    total: float


class EconomicsReport(BaseModel):
    """Mirrors ``economics.json`` (from :func:`samba.economics.cashflow.build_economics`).

    The per-year ``cashflow_annual`` table and the top-level scalars are the
    drift-sensitive contract the UI consumes. The cost breakdowns
    (``investment``, ``om_annual_npv``, …) are backend-internal aggregates kept
    loosely typed so internal accounting changes do not needlessly break the gate.
    """

    model_config = ConfigDict(extra="forbid")

    discount_rate_real: float
    project_lifetime_years: int
    crf: float
    npc: float

    investment: dict[str, float]
    replacement_schedule: dict[str, dict[str, float]]
    om_annual_npv: dict[str, float]
    fuel: dict[str, float]
    salvage: dict[str, float]
    grid: dict[str, float]
    gas: dict[str, float]

    cashflow_annual: list[CashflowYear]


class SizingRow(BaseModel):
    """One row of ``sizing.csv`` (the optimiser's chosen component sizing)."""

    model_config = ConfigDict(extra="forbid")

    component: str
    capacity: float
    unit: str
    count: int
    capital_cost: float


class DispatchContract(BaseModel):
    """Shape of the parsed ``dispatch.csv`` time-series the UI charts.

    The dispatch frame is wide and its columns vary by scenario, so this models
    the envelope (a timestamp index plus named numeric series) rather than a
    fixed column set. ``KNOWN_SERIES`` documents the series the UI knows how to
    label/colour; unknown series are still rendered generically.
    """

    model_config = ConfigDict(extra="forbid")

    timestamps: list[str]
    series: dict[str, list[float]]


#: Dispatch series the UI has explicit labels/colours for (others render generically).
KNOWN_DISPATCH_SERIES: tuple[str, ...] = (
    "eload",
    "pv_gen",
    "wt_gen",
    "dg_gen",
    "grid_buy",
    "grid_sell",
    "batt_charge",
    "batt_discharge",
    "batt_soc",
    "unmet_load",
)
