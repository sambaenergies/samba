# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Electrical-domain extractor implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

from samba.solver._extract_helpers import (
    _col,
    _get_battery_capacity,
    _invest_flow_capacity,
    _invest_or_fixed_flow,
    _node_col,
)

if TYPE_CHECKING:
    from samba.solver.extract import ComponentExtractionParams

__all__ = [
    "_BatteryExtractor",
    "_DGExtractor",
    "_EVExtractor",
    "_ElectricalCoreExtractor",
    "_GridExtractor",
    "_InverterExtractor",
    "_PVExtractor",
    "_WindExtractor",
]


class _ElectricalCoreExtractor:
    """Extract core AC/DC bus flows: ``eload``, ``unmet_load``, ``energy_dump``."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]:
        ac_bus = groups.get("ac_bus")
        dc_bus = groups.get("dc_bus")
        load_node = groups.get("load")
        unmet_node = groups.get("unmet_load")
        dc_dump_node = groups.get("dc_dump")
        ac_dump_node = groups.get("ac_dump")

        eload = _col(ac_bus, load_node, flow_df, timeindex)
        unmet_load = _col(unmet_node, ac_bus, flow_df, timeindex)
        energy_dump = _col(dc_bus, dc_dump_node, flow_df, timeindex) + _col(
            ac_bus, ac_dump_node, flow_df, timeindex
        )
        return {
            "eload": eload,
            "unmet_load": unmet_load,
            "energy_dump": energy_dump,
        }, {}


class _PVExtractor:
    """Extract PV generation and PV capacity."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]:
        pv_node = groups.get("pv")
        dc_bus = groups.get("dc_bus")

        pv_gen = _col(pv_node, dc_bus, flow_df, timeindex)

        caps: dict[str, float] = {}
        if pv_node is not None and dc_bus is not None:
            cap = _invest_or_fixed_flow(pv_node, dc_bus, "outputs", invest_df, pv_node)
            if cap is not None:
                caps["pv_kw"] = cap

        return {"pv_gen": pv_gen}, caps


class _BatteryExtractor:
    """Extract battery charge/discharge/SOC flows and battery capacity."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]:
        batt_node = groups.get("battery")
        dc_bus = groups.get("dc_bus")

        batt_charge = _col(dc_bus, batt_node, flow_df, timeindex)
        batt_discharge = _col(batt_node, dc_bus, flow_df, timeindex)

        if batt_node is not None and soc_df is not None:
            soc_series = _node_col(soc_df, batt_node)
            if soc_series is not None:
                batt_energy: pd.Series = soc_series.iloc[:-1].set_axis(timeindex).astype(float)
            else:
                batt_energy = pd.Series(0.0, index=timeindex, dtype=float)
        else:
            batt_energy = pd.Series(0.0, index=timeindex, dtype=float)

        batt_capacity = _get_battery_capacity(batt_node, invest_df)
        if batt_capacity > 0.0:
            batt_soc = (batt_energy / batt_capacity).clip(0.0, 1.0)
        else:
            batt_soc = pd.Series(0.0, index=timeindex, dtype=float)

        cols = {
            "batt_charge": batt_charge,
            "batt_discharge": batt_discharge,
            "batt_soc": batt_soc,
            "battery_soc_kwh": batt_energy,
        }
        caps: dict[str, float] = {}
        if batt_node is not None:
            kwh = _get_battery_capacity(batt_node, invest_df)
            if kwh > 0:
                caps["battery_kwh"] = kwh
            batt_kw = _invest_flow_capacity(dc_bus, batt_node, invest_df)
            if batt_kw is not None:
                caps["battery_kw"] = batt_kw
        return cols, caps


class _InverterExtractor:
    """Extract inverter DC->AC and AC->DC flows and inverter capacity."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]:
        inv_node = groups.get("inverter")
        ac_bus = groups.get("ac_bus")

        inverter_dc_to_ac = _col(inv_node, ac_bus, flow_df, timeindex)
        inverter_ac_to_dc = pd.Series(0.0, index=timeindex, dtype=float)

        caps: dict[str, float] = {}
        if inv_node is not None and ac_bus is not None:
            cap = _invest_or_fixed_flow(inv_node, ac_bus, "outputs", invest_df, inv_node)
            if cap is not None:
                caps["inverter_kw"] = cap

        return {
            "inverter_dc_to_ac": inverter_dc_to_ac,
            "inverter_ac_to_dc": inverter_ac_to_dc,
        }, caps


class _WindExtractor:
    """Extract wind turbine generation (DC-coupled) and WT capacity."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]:
        wt_node = groups.get("wind_turbine")
        dc_bus = groups.get("dc_bus")

        wt_gen = _col(wt_node, dc_bus, flow_df, timeindex)

        caps: dict[str, float] = {}
        if wt_node is not None and dc_bus is not None:
            cap = _invest_or_fixed_flow(wt_node, dc_bus, "outputs", invest_df, wt_node)
            if cap is not None:
                caps["wt_kw"] = cap

        return {"wt_gen": wt_gen}, caps


class _DGExtractor:
    """Extract diesel generator dispatch."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]:
        diesel_gen_node = groups.get("diesel_generator")
        ac_bus = groups.get("ac_bus")

        dg_gen = _col(diesel_gen_node, ac_bus, flow_df, timeindex)
        return {"dg_gen": dg_gen}, {}


class _GridExtractor:
    """Extract grid import (``grid_buy``) and export (``grid_sell``) flows."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]:
        grid_import_node = groups.get("grid_import")
        grid_export_node = groups.get("grid_export")
        ac_bus = groups.get("ac_bus")

        grid_buy = _col(grid_import_node, ac_bus, flow_df, timeindex)
        grid_sell = _col(ac_bus, grid_export_node, flow_df, timeindex)
        return {"grid_buy": grid_buy, "grid_sell": grid_sell}, {}


class _EVExtractor:
    """Extract EV charge/discharge/SOC/travel flows."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]:
        ac_bus = groups.get("ac_bus")
        ev_charger_node = groups.get("ev_charger")
        ev_v2g_node = groups.get("ev_v2g")
        ev_storage_node = groups.get("ev_storage")
        ev_bus_node = groups.get("ev_bus")
        ev_travel_node = groups.get("ev_travel")

        ev_charge = _col(ac_bus, ev_charger_node, flow_df, timeindex)
        ev_discharge = _col(ev_v2g_node, ac_bus, flow_df, timeindex)
        ev_travel = _col(ev_bus_node, ev_travel_node, flow_df, timeindex)

        if ev_storage_node is not None and soc_df is not None:
            ev_soc_series = _node_col(soc_df, ev_storage_node)
            if ev_soc_series is not None:
                ev_energy: pd.Series = ev_soc_series.iloc[:-1].set_axis(timeindex).astype(float)
            else:
                ev_energy = pd.Series(0.0, index=timeindex, dtype=float)
        else:
            ev_energy = pd.Series(0.0, index=timeindex, dtype=float)

        return {
            "ev_charge_kw": ev_charge,
            "ev_discharge_kw": ev_discharge,
            "ev_soc_kwh": ev_energy,
            "ev_travel_kwh": ev_travel,
        }, {}
