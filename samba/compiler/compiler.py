# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Main energy system compiler.

The :func:'compile_energy_system' function is the central entry point for
Phase 4.  It accepts a :class:'CompilerInputs' bundle, orchestrates all
component builders, and returns a fully specified ''solph.EnergySystem''
ready for the solver.

Bus topology
------------

Electrical::

    [PV Source] ----------------------+
    [Battery Storage] ----------------+  DC Bus --[Inverter Converter]--+
                                      (only if PV or battery enabled)   |
    [Wind Source] ------------------------------------------------- AC Bus --[Load Sink]
    [Diesel Fuel Bus + Converter] ---------------------------------------+
    [Grid Import Source] ------------------------------------------------+
    [Grid Export Sink (optional)] ---------------------------------------+

Thermal (added when heat_pump or gas_supply enabled)::

    [heat_unmet penalty source] --+
                                  +-- heat_bus --[heat_load sink]
    [HeatPump / GasBoiler] -------+

    [cool_unmet penalty source] --+
                                  +-- cool_bus --[cool_load sink]
    [HeatPump (cooling mode)] ----+

Bus creation is authoritative in :mod:'samba.compiler.buses'.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import oemof.solph as solph
import pandas as pd

from samba.compiler.annualize import crf, ep_costs, real_discount_rate  # noqa: F401 -- re-exported
from samba.compiler.builders.diesel import DieselBuilder
from samba.compiler.builders.ev import EVBuilder
from samba.compiler.builders.grid import GridBuilder
from samba.compiler.builders.heat_pump import HeatPumpBuilder
from samba.compiler.builders.inverter import InverterBuilder
from samba.compiler.builders.pv import PVBuilder
from samba.compiler.builders.thermal_load import ThermalLoadBuilder
from samba.compiler.builders.thermal_storage import ThermalStorageBuilder
from samba.compiler.builders.wind import WindBuilder
from samba.compiler.buses import build_buses
from samba.load_profiles.ev_presence import build_presence_schedule, load_presence_csv
from samba.load_profiles.thermal import load_thermal_loads
from samba.tariff import TariffArrays
from samba.thermal.cop import build_cop_arrays

if TYPE_CHECKING:
    from samba.scenario.models import Scenario
    from samba.weather.models import WeatherData

log = logging.getLogger(__name__)

__all__ = [
    "CompilerInputs",
    "ConfigurationError",
    "ThermalPeaks",
    "compile_energy_system",
    "precompute_thermal_peaks",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConfigurationError(Exception):
    """Raised when the scenario configuration is invalid for compilation.

    Typically indicates a logical inconsistency that the Pydantic schema
    validators do not (or cannot) catch -- for example, requesting
    ''force_grid_disconnect'' while grid is the only generation source.
    """


# ---------------------------------------------------------------------------
# Thermal peak pre-computation (used by HeatPumpBuilder for catalog selection)
# ---------------------------------------------------------------------------


@dataclass
class ThermalPeaks:
    """Peak thermal demands for HP catalog model selection.

    These are computed from thermal load CSV files (Phase 22) before any
    component builder runs.  When no thermal load is configured, both fields
    default to 0.0 -- the HP builder will select the smallest catalog model.
    """

    peak_heating_kw: float = 0.0
    peak_cooling_kw: float = 0.0


def precompute_thermal_peaks(
    scenario: Scenario,
    t_outdoor: np.ndarray | None = None,
    *,
    base_dir: Path | None = None,
) -> ThermalPeaks:
    """Compute peak thermal demands for HP catalog model selection.

    Delegates to :func:`~samba.load_profiles.thermal.load_thermal_loads` so
    both ``'csv'`` and ``'degree_day'`` sources are supported.

    Called from :func:`compile_energy_system` just before the HP builder so
    that :func:`~samba.thermal.cop.build_cop_arrays` can select the correct
    catalog model.

    Parameters
    ----------
    scenario:
        Validated scenario configuration.
    t_outdoor:
        Hourly outdoor temperature array [°C], shape ``(8760,)``.  Required
        when ``thermal.source == 'degree_day'``; ignored for ``'csv'``.
    base_dir:
        Base directory used to resolve relative thermal CSV paths.  When
        ``None`` the paths are used as-is (absolute or relative to CWD).

    Returns
    -------
    ThermalPeaks
        ``ThermalPeaks(0.0, 0.0)`` when no thermal load is configured.
    """
    thermal_load = getattr(getattr(scenario, "load", None), "thermal", None)
    if thermal_load is None or not getattr(thermal_load, "enabled", True):
        return ThermalPeaks()

    tl = load_thermal_loads(thermal_load, t_outdoor, base_dir=base_dir)
    peaks = ThermalPeaks(
        peak_heating_kw=tl.peak_heating_kw,
        peak_cooling_kw=tl.peak_cooling_kw,
    )
    log.debug(
        "Thermal peaks: heating=%.1f kW, cooling=%.1f kW",
        peaks.peak_heating_kw,
        peaks.peak_cooling_kw,
    )
    return peaks


# ---------------------------------------------------------------------------
# Input bundle
# ---------------------------------------------------------------------------


@dataclass
class CompilerInputs:
    """All inputs required to build an ''oemof.solph.EnergySystem''.

    Attributes
    ----------
    scenario:
        Validated scenario configuration.
    load_kw:
        Hourly electrical load demand in kW, shape ''(8760,)''.
    tariff_arrays:
        Pre-resolved tariff arrays from :func:'samba.tariff.resolve_tariff'.
    weather:
        Parsed weather dataset.  Always required: v3 thermal component builders
        use hourly ambient temperature; callers without PV/wind may construct a
        zero-filled stub via :func:'samba.weather.stub_weather'.
    pv_per_kwp:
        Normalized PV output fractions per kWp installed (0-1), shape
        ''(8760,)''.  Required when ''scenario.components.pv'' is not ''None''.
    wind_power_kw:
        Per-turbine hourly wind power in kW, shape ''(8760,)''.  Required when
        ''scenario.components.wind_turbine'' is not ''None''.
    """

    scenario: Scenario
    load_kw: np.ndarray
    tariff_arrays: TariffArrays
    weather: WeatherData
    pv_per_kwp: np.ndarray | None = field(default=None)
    wind_power_kw: np.ndarray | None = field(default=None)
    scenario_dir: Path | None = field(default=None)  # base dir for relative thermal CSV paths


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------


def compile_energy_system(inputs: CompilerInputs) -> solph.EnergySystem:
    """Build and return a fully specified ''solph.EnergySystem''.

    Parameters
    ----------
    inputs:
        All data tensors and the validated scenario configuration.

    Returns
    -------
    solph.EnergySystem
        Populated energy system, ready to be passed to ''solph.Model''
        (Phase 5).

    Raises
    ------
    ConfigurationError
        If the scenario is logically inconsistent (e.g. no generation source,
        or ''force_grid_disconnect'' conflicts with component mix).
    ValueError
        If a required time-series array is ''None'' for an enabled component.
    """
    scenario = inputs.scenario
    _validate_inputs(inputs)

    timeindex = _build_timeindex(scenario.project.year)
    energy_system = solph.EnergySystem(timeindex=timeindex, infer_last_interval=True)
    log.debug("Created EnergySystem -- timeindex length=%d", len(timeindex))

    bus_set = build_buses(scenario, energy_system)
    nodes: list[solph.network.Node] = []
    log.debug(
        "Buses created -- ac=True, dc=%s, heat=%s, cool=%s",
        bus_set.dc is not None,
        bus_set.thermal.has_heating,
        bus_set.thermal.has_cooling,
    )

    _add_dc_side_components(nodes, inputs, bus_set)
    _add_ac_side_components(nodes, inputs, bus_set, timeindex)
    _add_thermal_domain(nodes, inputs, bus_set, timeindex)
    _add_heat_pump(nodes, inputs, bus_set, timeindex)
    _add_thermal_storage(nodes, inputs, bus_set)
    _add_gas_supply(nodes, inputs, bus_set)
    _add_load_unmet_and_dump(nodes, inputs, bus_set, timeindex)

    energy_system.add(*nodes)
    _log_compiled_system(bus_set, nodes)
    return energy_system


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_timeindex(project_year: int) -> pd.DatetimeIndex:
    """Return the standard 8 760-hour simulation index for *project_year*."""
    return pd.date_range(
        start=f"{project_year}-01-01 00:00",
        periods=8760,
        freq="h",
    )


def _add_dc_side_components(
    nodes: list[solph.network.Node],
    inputs: CompilerInputs,
    bus_set: Any,
) -> None:
    """Add PV, battery, and inverter nodes when their buses/components are active."""
    scenario = inputs.scenario
    comps = scenario.components

    if comps.pv is not None and comps.pv.enabled:
        if inputs.pv_per_kwp is None:
            raise ConfigurationError(
                "PV is enabled but pv_per_kwp was not resolved. "
                "Check that weather data and irradiance CSV are provided."
            )
        nodes.extend(
            PVBuilder().build(
                scenario,
                bus_set.dc,
                bus_set.ac,
                pv_power_per_kwp=inputs.pv_per_kwp,
            )
        )
        log.debug("Added PV nodes")

    if comps.battery is not None and comps.battery.enabled:
        from samba.batteries.factory import build_battery_storage

        nodes.extend(build_battery_storage(scenario, bus_set.dc, bus_set.ac))
        log.debug("Added Battery nodes -- chemistry=%s", comps.battery.chemistry)

    if bus_set.dc is not None:
        nodes.extend(InverterBuilder().build(scenario, bus_set.dc, bus_set.ac))
        log.debug("Added Inverter nodes")


def _add_ac_side_components(
    nodes: list[solph.network.Node],
    inputs: CompilerInputs,
    bus_set: Any,
    timeindex: pd.DatetimeIndex,
) -> None:
    """Add wind, diesel, grid, and EV nodes."""
    scenario = inputs.scenario
    comps = scenario.components
    constraints = scenario.constraints

    alpha: float = scenario.objective.emissions_weight
    if alpha > 0.0:
        log.debug("Multi-objective mode: emissions_weight=%.4f $/kg CO2", alpha)

    if comps.wind_turbine is not None and comps.wind_turbine.enabled:
        if inputs.wind_power_kw is None:
            raise ConfigurationError(
                "WindTurbine is enabled but wind_power_kw was not resolved. "
                "Check that weather data and wind speed CSV are provided."
            )
        nodes.extend(
            WindBuilder().build(
                scenario,
                bus_set.dc,
                bus_set.ac,
                wind_power_kw=inputs.wind_power_kw,
            )
        )
        log.debug("Added Wind nodes")

    if comps.diesel_generator is not None and comps.diesel_generator.enabled:
        nodes.extend(DieselBuilder().build(scenario, bus_set.dc, bus_set.ac, alpha=alpha))
        log.debug("Added Diesel nodes")

    if comps.grid is not None and comps.grid.enabled and not constraints.force_grid_disconnect:
        endogenous_tiering = scenario.tariff.buy.endogenous_tiering
        cbuy_for_grid = (
            np.zeros_like(inputs.tariff_arrays.cbuy)
            if endogenous_tiering
            else inputs.tariff_arrays.cbuy
        )
        nodes.extend(
            GridBuilder().build(
                scenario,
                bus_set.dc,
                bus_set.ac,
                cbuy=cbuy_for_grid,
                csell=inputs.tariff_arrays.csell,
                alpha=alpha,
            )
        )
        if endogenous_tiering:
            log.debug(
                "Added Grid nodes (endogenous tiered tariff -- cbuy zeroed for PWL injection)"
            )
        else:
            log.debug("Added Grid nodes")

    if comps.ev is not None and comps.ev.enabled:
        ev = comps.ev
        if ev.presence_source == "csv":
            if ev.presence_csv_path is None:
                raise ConfigurationError(
                    "EV.presence_source='csv' requires presence_csv_path to be set."
                )
            presence = load_presence_csv(ev.presence_csv_path)
        else:
            presence = build_presence_schedule(
                arrival_hour=ev.arrival_hour,
                departure_hour=ev.departure_hour,
                workdays_per_week=ev.workdays_per_week,
                year=scenario.project.year,
            )
        nodes.extend(
            EVBuilder().build(
                scenario,
                bus_set.ac,
                presence=presence,
                csell=inputs.tariff_arrays.csell,
                timeindex=timeindex,
            )
        )
        log.debug("Added EV nodes (V2G=%s)", ev.v2g_enabled)


def _add_thermal_domain(
    nodes: list[solph.network.Node],
    inputs: CompilerInputs,
    bus_set: Any,
    timeindex: pd.DatetimeIndex,
) -> None:
    """Add thermal unmet/load nodes."""
    scenario = inputs.scenario
    thermal_penalty = 1e6

    if bus_set.thermal.has_heating:
        nodes.append(
            solph.components.Source(
                label="heat_unmet",
                outputs={bus_set.thermal.heating: solph.Flow(variable_costs=thermal_penalty)},
            )
        )
    if bus_set.thermal.has_cooling:
        nodes.append(
            solph.components.Source(
                label="cool_unmet",
                outputs={bus_set.thermal.cooling: solph.Flow(variable_costs=thermal_penalty)},
            )
        )

    thermal_cfg = getattr(getattr(scenario, "load", None), "thermal", None)
    if thermal_cfg is not None and thermal_cfg.enabled:
        thermal_loads = load_thermal_loads(
            thermal_cfg, inputs.weather.tamb_c, base_dir=inputs.scenario_dir
        )
        nodes.extend(ThermalLoadBuilder().build(scenario, bus_set, thermal_loads))
        log.debug(
            "Added ThermalLoad Sinks: heating=%.1f kWh_th/yr, cooling=%.1f kWh_th/yr",
            thermal_loads.annual_heating_kwh_th,
            thermal_loads.annual_cooling_kwh_th,
        )
        return

    if bus_set.thermal.has_heating:
        nodes.append(
            solph.components.Sink(
                label="heat_load",
                inputs={
                    bus_set.thermal.heating: solph.Flow(
                        fix=np.zeros(len(timeindex)),
                        nominal_capacity=1.0,
                    )
                },
            )
        )
        log.debug("Added thermal heating placeholder Sink (no ThermalLoad configured)")
    if bus_set.thermal.has_cooling:
        nodes.append(
            solph.components.Sink(
                label="cool_load",
                inputs={
                    bus_set.thermal.cooling: solph.Flow(
                        fix=np.zeros(len(timeindex)),
                        nominal_capacity=1.0,
                    )
                },
            )
        )
        log.debug("Added thermal cooling placeholder Sink (no ThermalLoad configured)")


def _add_heat_pump(
    nodes: list[solph.network.Node],
    inputs: CompilerInputs,
    bus_set: Any,
    timeindex: pd.DatetimeIndex,
) -> None:
    """Add heat pump nodes when enabled."""
    scenario = inputs.scenario
    comps = scenario.components

    if comps.heat_pump is None or not comps.heat_pump.enabled:
        return

    thermal_peaks = precompute_thermal_peaks(
        scenario,
        t_outdoor=inputs.weather.tamb_c,
        base_dir=inputs.scenario_dir,
    )
    cop_arrays = build_cop_arrays(
        hp=comps.heat_pump,
        t_outdoor=inputs.weather.tamb_c,
        peak_heating_kw=thermal_peaks.peak_heating_kw,
        peak_cooling_kw=thermal_peaks.peak_cooling_kw,
        base_dir=inputs.scenario_dir,
    )
    nodes.extend(
        HeatPumpBuilder().build(
            scenario,
            bus_set,
            cop_arrays,
            n_timesteps=len(timeindex),
        )
    )
    log.debug(
        "Added HeatPump nodes -- model=%s (%d BTU/hr), mode=%s",
        cop_arrays.model_name,
        cop_arrays.model_btu,
        comps.heat_pump.mode,
    )


def _add_thermal_storage(
    nodes: list[solph.network.Node],
    inputs: CompilerInputs,
    bus_set: Any,
) -> None:
    """Add thermal storage nodes when enabled."""
    scenario = inputs.scenario
    comps = scenario.components

    if comps.thermal_storage is None or not comps.thermal_storage.enabled:
        return

    nodes.extend(ThermalStorageBuilder().build(scenario, bus_set))
    log.debug("Added ThermalStorage nodes -- sizing=%s", comps.thermal_storage.sizing)


def _add_gas_supply(
    nodes: list[solph.network.Node],
    inputs: CompilerInputs,
    bus_set: Any,
) -> None:
    """Add gas supply / boiler nodes when enabled."""
    scenario = inputs.scenario
    comps = scenario.components

    if comps.gas_supply is None or not comps.gas_supply.enabled:
        return

    from samba.compiler.builders.gas_supply import GasSupplyBuilder
    from samba.tariff.gas import build_gas_rate_array

    gas_rate_array = build_gas_rate_array(comps.gas_supply.tariff)
    nodes.extend(GasSupplyBuilder().build(scenario, bus_set, gas_rate_array))
    log.debug(
        "Added GasSupply nodes (boiler_efficiency=%.2f, max_output_kw_th=%s)",
        comps.gas_supply.boiler_efficiency,
        comps.gas_supply.max_output_kw_th,
    )


def _add_load_unmet_and_dump(
    nodes: list[solph.network.Node],
    inputs: CompilerInputs,
    bus_set: Any,
    timeindex: pd.DatetimeIndex,
) -> None:
    """Add required load sink, unmet-load source, and curtailment sinks."""
    scenario = inputs.scenario
    constraints = scenario.constraints

    peak_load = float(np.max(inputs.load_kw))
    if peak_load <= 0.0:
        raise ConfigurationError("load_kw array must contain positive values")
    load_profile = inputs.load_kw / peak_load

    nodes.append(
        solph.components.Sink(
            label="load",
            inputs={bus_set.ac: solph.Flow(fix=load_profile, nominal_capacity=peak_load)},
        )
    )
    log.debug("Added Load sink (peak=%.2f kW)", peak_load)

    if constraints.max_lpsp > 0.0:
        penalty_cost = 1e4
        nodes.append(
            solph.components.Source(
                label="unmet_load",
                outputs={bus_set.ac: solph.Flow(variable_costs=penalty_cost)},
            )
        )
        log.debug("Added unmet_load penalty source (max_lpsp=%.4f)", constraints.max_lpsp)

    if bus_set.dc is not None:
        nodes.append(
            solph.components.Sink(
                label="dc_dump",
                inputs={bus_set.dc: solph.Flow()},
            )
        )

    nodes.append(
        solph.components.Sink(
            label="ac_dump",
            inputs={bus_set.ac: solph.Flow()},
        )
    )
    log.debug(
        "Added%s ac_dump curtailment sink(s)",
        " dc_dump and" if bus_set.dc is not None else "",
    )


def _log_compiled_system(bus_set: Any, nodes: list[solph.network.Node]) -> None:
    """Log final compiled-system summary with bus/component counts."""
    n_buses = sum(
        1
        for bus in [
            bus_set.ac,
            bus_set.dc,
            bus_set.fuel,
            bus_set.thermal.heating,
            bus_set.thermal.cooling,
            bus_set.thermal.gas,
        ]
        if bus is not None
    )
    log.info(
        "Compiled EnergySystem with %d nodes (%d buses + %d components)",
        len(nodes) + n_buses,
        n_buses,
        len(nodes),
    )


def _validate_inputs(inputs: CompilerInputs) -> None:
    """Raise :exc:'ConfigurationError' or :exc:'ValueError' on bad inputs."""
    scenario = inputs.scenario
    comps = scenario.components
    constraints = scenario.constraints

    # PV array provided when PV is enabled
    if comps.pv is not None and comps.pv.enabled and inputs.pv_per_kwp is None:
        raise ValueError("inputs.pv_per_kwp must be provided when pv is enabled")

    # Wind array provided when wind is enabled
    if (
        comps.wind_turbine is not None
        and comps.wind_turbine.enabled
        and inputs.wind_power_kw is None
    ):
        raise ValueError("inputs.wind_power_kw must be provided when wind_turbine is enabled")

    # force_grid_disconnect + grid as sole generation source
    if constraints.force_grid_disconnect:
        has_other_gen = any(
            [
                comps.pv is not None and comps.pv.enabled,
                comps.wind_turbine is not None and comps.wind_turbine.enabled,
                comps.diesel_generator is not None and comps.diesel_generator.enabled,
            ]
        )
        if not has_other_gen:
            raise ConfigurationError(
                "force_grid_disconnect=True but no other generation source "
                "(pv, wind_turbine, or diesel_generator) is enabled. "
                "The system would have no supply."
            )

    # Load array shape
    if inputs.load_kw.shape != (8760,):
        raise ValueError(f"load_kw must have shape (8760,); got {inputs.load_kw.shape}")
