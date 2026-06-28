# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Thermal-domain extractor implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

from samba.solver._extract_helpers import (
    _col,
    _get_battery_capacity,
    _node_col,
)

if TYPE_CHECKING:
    from samba.solver.extract import ComponentExtractionParams

__all__ = [
    "_GasBoilerExtractor",
    "_HeatPumpExtractor",
    "_ThermalBusExtractor",
    "_ThermalStorageExtractor",
]


class _ThermalBusExtractor:
    """Extract thermal unmet/load columns when heat/cool buses are present."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]:
        cols: dict[str, pd.Series] = {}
        heat_bus = groups.get("heat_bus")
        cool_bus = groups.get("cool_bus")
        if heat_bus is None and cool_bus is None:
            return cols, {}

        if heat_bus is not None:
            heat_unmet_node = groups.get("heat_unmet")
            heat_load_node = groups.get("heat_load")
            cols["heat_unmet_kw"] = _col(heat_unmet_node, heat_bus, flow_df, timeindex)
            cols["heat_load_kw"] = _col(heat_bus, heat_load_node, flow_df, timeindex)
        if cool_bus is not None:
            cool_unmet_node = groups.get("cool_unmet")
            cool_load_node = groups.get("cool_load")
            cols["cool_unmet_kw"] = _col(cool_unmet_node, cool_bus, flow_df, timeindex)
            cols["cool_load_kw"] = _col(cool_bus, cool_load_node, flow_df, timeindex)
        return cols, {}


class _HeatPumpExtractor:
    """Extract heat pump heating/cooling and electrical draw columns."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]:
        cols: dict[str, pd.Series] = {}

        hp_heater = groups.get("hp_heater")
        hp_cooler = groups.get("hp_cooler")
        hp_standby = groups.get("hp_standby")

        if hp_heater is None and hp_cooler is None:
            return cols, {}

        ac_bus = groups.get("ac_bus")
        heat_bus = groups.get("heat_bus")
        cool_bus = groups.get("cool_bus")

        if hp_heater is not None:
            cols["hp_elec_heating_kw"] = _col(ac_bus, hp_heater, flow_df, timeindex)
            cols["hp_heating_kw"] = _col(hp_heater, heat_bus, flow_df, timeindex)

        if hp_cooler is not None:
            cols["hp_elec_cooling_kw"] = _col(ac_bus, hp_cooler, flow_df, timeindex)
            cols["hp_cooling_kw"] = _col(hp_cooler, cool_bus, flow_df, timeindex)

        if hp_standby is not None:
            cols["hp_standby_kw"] = _col(ac_bus, hp_standby, flow_df, timeindex)

        return cols, {}


class _ThermalStorageExtractor:
    """Extract thermal storage charge/discharge/level columns."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]:
        cols: dict[str, pd.Series] = {}
        caps: dict[str, float] = {}

        hs_node = groups.get("thermal_storage_heating")
        cs_node = groups.get("thermal_storage_cooling")

        if hs_node is None and cs_node is None:
            return cols, caps

        heat_bus = groups.get("heat_bus")
        cool_bus = groups.get("cool_bus")
        zero = pd.Series(0.0, index=timeindex, dtype=float)

        def _extract_storage(node: Any, bus: Any, prefix: str) -> None:
            cols[f"{prefix}_charge_kw"] = _col(bus, node, flow_df, timeindex)
            cols[f"{prefix}_discharge_kw"] = _col(node, bus, flow_df, timeindex)
            level = zero.copy()
            if soc_df is not None:
                soc_series = _node_col(soc_df, node)
                if soc_series is not None:
                    level = soc_series.iloc[:-1].set_axis(timeindex).astype(float)
            cols[f"{prefix}_level_kwh_th"] = level
            cap = _get_battery_capacity(node, invest_df)
            if cap > 0:
                caps[f"{prefix}_kwh_th"] = cap

        if hs_node is not None and heat_bus is not None:
            _extract_storage(hs_node, heat_bus, "thermal_storage_heating")
        if cs_node is not None and cool_bus is not None:
            _extract_storage(cs_node, cool_bus, "thermal_storage_cooling")

        return cols, caps


class _GasBoilerExtractor:
    """Extract gas boiler input/output thermal dispatch columns."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]:
        gas_boiler = groups.get("gas_boiler")
        if gas_boiler is None:
            return {}, {}

        gas_bus = groups.get("gas_bus")
        heat_bus = groups.get("heat_bus")

        cols: dict[str, pd.Series] = {
            "gas_boiler_input_kw_th": _col(gas_bus, gas_boiler, flow_df, timeindex),
            "gas_boiler_output_kw_th": _col(gas_boiler, heat_bus, flow_df, timeindex),
        }
        return cols, {}
