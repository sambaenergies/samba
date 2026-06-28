# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Dispatch extraction from oemof-solph ``Results`` objects.

Converts solver results into a structured :class:`DispatchResult` whose
``dispatch`` DataFrame matches the SAMBA results contract.

Node label conventions (set by builders in ``samba.compiler.builders``):
    - ``"dc_bus"``             -- DC system bus
    - ``"ac_bus"``             -- AC system bus
    - ``"heat_bus"``           -- Heating thermal bus (kWh_th)
    - ``"cool_bus"``           -- Cooling thermal bus (kWh_th)
    - ``"gas_bus"``            -- Natural gas bus (kWh_th, LHV)
    - ``"pv"``                 -- PV source (DC side)
    - ``"battery"``            -- GenericStorage (DC bus)
    - ``"inverter"``           -- Converter (DC -> AC)
    - ``"wind_turbine"``       -- Wind source (DC bus, DC-coupled -- P_RE = Ppv + Pwt)
    - ``"diesel_generator"``   -- Diesel converter (-> AC bus)
    - ``"grid_import"``        -- Grid import source (-> AC bus)
    - ``"grid_export"``        -- Grid export sink (<- AC bus)
    - ``"load"``               -- Load sink (<- AC bus)
    - ``"unmet_load"``         -- Unmet-load penalty source (-> AC bus)
    - ``"dc_dump"``            -- DC curtailment sink (<- DC bus)
    - ``"ac_dump"``            -- AC curtailment sink (<- AC bus)
    - ``"ev_charger"``         -- EV charger Converter (AC bus -> ev_bus, presence-gated)
    - ``"ev_storage"``         -- EV GenericStorage (ev_bus <-> ev_bus)
    - ``"ev_v2g"``             -- V2G Converter (ev_bus -> AC bus, optional)
    - ``"ev_bus"``             -- dedicated internal EV bus
    - ``"ev_travel"``          -- travel depletion Sink (<- ev_bus)
    - ``"heat_unmet"``         -- thermal unmet-demand penalty source (-> heat_bus)
    - ``"heat_load"``          -- thermal load sink (<- heat_bus)
    - ``"cool_unmet"``         -- thermal unmet-demand penalty source (-> cool_bus)
    - ``"cool_load"``          -- thermal load sink (<- cool_bus)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from samba.solver.component_extractors import (
    _BatteryExtractor,
    _DGExtractor,
    _ElectricalCoreExtractor,
    _EVExtractor,
    _GasBoilerExtractor,
    _GridExtractor,
    _HeatPumpExtractor,
    _InverterExtractor,
    _PVExtractor,
    _ThermalBusExtractor,
    _ThermalStorageExtractor,
    _WindExtractor,
)

log = logging.getLogger(__name__)

__all__ = [
    "DispatchResult",
    "EnergyBalanceError",
    "extract_dispatch",
    "validate_energy_balance",
]


@dataclass
class DispatchResult:
    """Structured result from the oemof-solph solve step.

    Attributes
    ----------
    dispatch:
        ``pd.DataFrame`` with 8 760 rows (one per hour) and columns exactly
        matching the results contract.
    capacities:
        Dictionary mapping component label to optimal capacity. Keys:
        ``"pv_kw"``, ``"battery_kwh"``, ``"battery_kw"``, ``"inverter_kw"``,
        ``"wt_kw"``.
    """

    dispatch: pd.DataFrame
    capacities: dict[str, float] = field(default_factory=dict)


@dataclass
class ComponentExtractionParams:
    """Immutable context passed to every component extractor."""

    timesteps: int
    capacities: dict[str, float] = field(default_factory=dict)


@runtime_checkable
class ComponentExtractor(Protocol):
    """Interface for per-component dispatch extraction."""

    def extract(
        self,
        groups: dict[str, Any],
        flow_df: pd.DataFrame,
        soc_df: pd.DataFrame | None,
        invest_df: pd.DataFrame | None,
        timeindex: pd.DatetimeIndex,
        params: ComponentExtractionParams,
    ) -> tuple[dict[str, pd.Series], dict[str, float]]: ...


_EXTRACTOR_REGISTRY: dict[str, ComponentExtractor] = {
    "electrical_core": _ElectricalCoreExtractor(),
    "pv": _PVExtractor(),
    "battery": _BatteryExtractor(),
    "inverter": _InverterExtractor(),
    "wind": _WindExtractor(),
    "diesel_generator": _DGExtractor(),
    "grid": _GridExtractor(),
    "ev": _EVExtractor(),
    "thermal_bus": _ThermalBusExtractor(),
    "heat_pump": _HeatPumpExtractor(),
    "thermal_storage": _ThermalStorageExtractor(),
    "gas_boiler": _GasBoilerExtractor(),
}

_EXTRACTORS: list[ComponentExtractor] = list(_EXTRACTOR_REGISTRY.values())

_EXTRACTOR_ORDER: list[str] = [
    "electrical_core",
    "pv",
    "battery",
    "inverter",
    "wind",
    "diesel_generator",
    "grid",
    "ev",
    "thermal_bus",
    "heat_pump",
    "thermal_storage",
    "gas_boiler",
]

# Guard accidental re-ordering between the named registry and list order.
if list(_EXTRACTOR_REGISTRY) != _EXTRACTOR_ORDER:  # pragma: no cover
    raise RuntimeError("Extractor registry insertion order changed unexpectedly.")


def extract_dispatch(
    energy_system: Any,
    results: Any,
) -> DispatchResult:
    """Extract dispatch time series and optimal capacities from solve results."""
    groups = energy_system.groups

    flow_df: pd.DataFrame | None = results.get("flow")
    invest_df: pd.DataFrame | None = results.get("invest")
    soc_df: pd.DataFrame | None = results.get("storage_content")

    if flow_df is None or flow_df.empty:
        raise ValueError("results.get('flow') returned empty DataFrame -- solve may not have run")

    timeindex: pd.DatetimeIndex = flow_df.index
    params = ComponentExtractionParams(timesteps=len(timeindex))

    all_cols: dict[str, pd.Series] = {}
    combined_caps: dict[str, float] = {}

    for extractor in _EXTRACTORS:
        cols, caps = extractor.extract(groups, flow_df, soc_df, invest_df, timeindex, params)
        all_cols.update(cols)
        combined_caps.update(caps)

    zero = pd.Series(0.0, index=timeindex, dtype=float)

    def _get(name: str) -> pd.Series:
        return all_cols.get(name, zero)

    dispatch = pd.DataFrame(
        {
            "eload": _get("eload").values,
            "pv_gen": _get("pv_gen").values,
            "wt_gen": _get("wt_gen").values,
            "dg_gen": _get("dg_gen").values,
            "grid_buy": _get("grid_buy").values,
            "grid_sell": _get("grid_sell").values,
            "batt_charge": _get("batt_charge").values,
            "batt_discharge": _get("batt_discharge").values,
            "batt_soc": _get("batt_soc").values,
            "battery_soc_kwh": _get("battery_soc_kwh").values,
            "unmet_load": _get("unmet_load").values,
            "energy_dump": _get("energy_dump").values,
            "inverter_dc_to_ac": _get("inverter_dc_to_ac").values,
            "inverter_ac_to_dc": _get("inverter_ac_to_dc").values,
            "ev_charge_kw": _get("ev_charge_kw").values,
            "ev_discharge_kw": _get("ev_discharge_kw").values,
            "ev_soc_kwh": _get("ev_soc_kwh").values,
            "ev_travel_kwh": _get("ev_travel_kwh").values,
        },
        index=timeindex,
    )

    for thermal_col in ("heat_unmet_kw", "heat_load_kw", "cool_unmet_kw", "cool_load_kw"):
        if thermal_col in all_cols:
            dispatch[thermal_col] = all_cols[thermal_col].values

    for hp_col in (
        "hp_elec_heating_kw",
        "hp_heating_kw",
        "hp_elec_cooling_kw",
        "hp_cooling_kw",
        "hp_standby_kw",
    ):
        if hp_col in all_cols:
            dispatch[hp_col] = all_cols[hp_col].values

    for ts_col in (
        "thermal_storage_heating_charge_kw",
        "thermal_storage_heating_discharge_kw",
        "thermal_storage_heating_level_kwh_th",
        "thermal_storage_cooling_charge_kw",
        "thermal_storage_cooling_discharge_kw",
        "thermal_storage_cooling_level_kwh_th",
    ):
        if ts_col in all_cols:
            dispatch[ts_col] = all_cols[ts_col].values

    for gas_col in ("gas_boiler_input_kw_th", "gas_boiler_output_kw_th"):
        if gas_col in all_cols:
            dispatch[gas_col] = all_cols[gas_col].values

    dispatch.index.name = "timestamp"

    log.info(
        "Extracted dispatch: %d rows, %d columns. Capacities: %s",
        len(dispatch),
        len(dispatch.columns),
        {k: f"{v:.2f}" for k, v in combined_caps.items()},
    )
    return DispatchResult(dispatch=dispatch, capacities=combined_caps)


class EnergyBalanceError(Exception):
    """Raised when solved dispatch violates the AC-side energy balance constraint."""

    def __init__(self, max_imbalance: float, tolerance_kwh: float) -> None:
        self.max_imbalance = max_imbalance
        self.tolerance_kwh = tolerance_kwh
        super().__init__(
            f"Energy balance violation: max hourly imbalance = {max_imbalance:.4f} kWh "
            f"(tolerance = {tolerance_kwh} kWh). Check solver output for infeasibility."
        )


def validate_energy_balance(
    dispatch: pd.DataFrame,
    tolerance_kwh: float = 1.0,
) -> None:
    """Check AC-side generation/consumption balance at each timestep."""
    ev_discharge = dispatch.get("ev_discharge_kw", pd.Series(0.0, index=dispatch.index))
    ac_supply = (
        dispatch["inverter_dc_to_ac"]
        + dispatch["dg_gen"]
        + dispatch["grid_buy"]
        + dispatch["unmet_load"]
        + ev_discharge
    )

    ev_charge = dispatch.get("ev_charge_kw", pd.Series(0.0, index=dispatch.index))
    ac_demand = dispatch["eload"] + dispatch["grid_sell"] + dispatch["energy_dump"] + ev_charge

    imbalance = (ac_supply - ac_demand).abs()
    max_imbalance = float(imbalance.max())

    if max_imbalance > tolerance_kwh:
        worst_hour = imbalance.idxmax()
        log.warning(
            "Energy balance violation at %s: imbalance=%.4f kWh (tolerance=%.1f kWh)",
            worst_hour,
            max_imbalance,
            tolerance_kwh,
        )
        raise EnergyBalanceError(max_imbalance, tolerance_kwh)

    log.info(
        "Energy balance OK -- max hourly imbalance = %.4f kWh (tolerance = %.1f kWh)",
        max_imbalance,
        tolerance_kwh,
    )
