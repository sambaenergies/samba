# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Heat pump component builder for oemof-solph.

Creates one or two ``solph.components.Converter`` objects per the HP
operating mode:

* ``"heating_only"`` -- one converter: AC bus -> heating bus
* ``"cooling_only"`` -- one converter: AC bus -> cooling bus
* ``"both"``         -- two converters: one per thermal bus

Each converter uses pre-computed hourly COP arrays from
:mod:`samba.thermal.cop` as time-varying ``conversion_factors``.

The LP formulation is:
    ``thermal_output[t] = COP[t] * elec_input[t]``
    ``thermal_output[t] <= rated_thermal_capacity_kw``

This is linear in ``elec_input[t]`` -- no approximation required.

An optional standby Sink is added to the AC bus when
``hp.standby_power_kw > 0``, representing always-on parasitic consumption
(controls, defrost cycle idle draw, etc.).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np
import oemof.solph as solph

if TYPE_CHECKING:
    from samba.compiler.buses import BusSet
    from samba.scenario.models import Scenario
    from samba.thermal.cop import COPArrays

log = logging.getLogger(__name__)

__all__ = ["HeatPumpBuilder"]


class HeatPumpBuilder:
    """Builds oemof nodes for the heat pump component."""

    def build(
        self,
        scenario: Scenario,
        bus_set: BusSet,
        cop_arrays: COPArrays,
        n_timesteps: int = 8760,
    ) -> list[Any]:
        """Return oemof nodes for the heat pump.

        Parameters
        ----------
        scenario:
            Validated scenario; ``scenario.components.heat_pump`` must not be
            ``None`` and must be enabled.
        bus_set:
            Bus container from :func:`~samba.compiler.buses.build_buses`.
            ``bus_set.thermal.heating`` / ``.cooling`` must exist for the
            requested mode.
        cop_arrays:
            Pre-computed :class:`~samba.thermal.cop.COPArrays` from
            :func:`~samba.thermal.cop.build_cop_arrays`.
        n_timesteps:
            Number of simulation timesteps (default 8 760 for annual hourly).

        Returns
        -------
        list of solph.network.Node
        """
        hp = scenario.components.heat_pump
        if hp is None or not hp.enabled:
            raise ValueError("HeatPumpBuilder.build called but heat_pump is not enabled")

        nodes: list[Any] = []
        mode = hp.mode

        # ------------------------------------------------------------------
        # Heating converter: AC bus -> heating bus
        # ------------------------------------------------------------------
        if mode in ("heating_only", "both"):
            if bus_set.thermal.heating is None:
                raise ValueError(
                    "HeatPumpBuilder: heat_bus is None but mode includes heating. "
                    "Ensure heat_pump.enabled=True so thermal buses are created."
                )
            if cop_arrays.heating is None:
                raise ValueError(
                    "HeatPumpBuilder: cop_arrays.heating is None but mode includes heating."
                )

            hp_heater: Any = solph.components.Converter(
                label="hp_heater",
                inputs={
                    bus_set.ac: solph.Flow(variable_costs=0.0),
                },
                outputs={
                    bus_set.thermal.heating: solph.Flow(
                        nominal_capacity=cop_arrays.heating_capacity_kw,
                    ),
                },
                conversion_factors={
                    bus_set.thermal.heating: solph.sequence(cop_arrays.heating),
                },
            )
            nodes.append(hp_heater)
            log.debug(
                "HP heater: AC -> heat_bus, rated=%.1f kW_th, mean_COP_h=%.2f, max_COP_h=%.2f",
                cop_arrays.heating_capacity_kw,
                float(np.mean(cop_arrays.heating)),
                float(np.max(cop_arrays.heating)),
            )

        # ------------------------------------------------------------------
        # Cooling converter: AC bus -> cooling bus
        # ------------------------------------------------------------------
        if mode in ("cooling_only", "both"):
            if bus_set.thermal.cooling is None:
                raise ValueError(
                    "HeatPumpBuilder: cool_bus is None but mode includes cooling. "
                    "Ensure heat_pump.enabled=True so thermal buses are created."
                )
            if cop_arrays.cooling is None:
                raise ValueError(
                    "HeatPumpBuilder: cop_arrays.cooling is None but mode includes cooling."
                )

            hp_cooler: Any = solph.components.Converter(
                label="hp_cooler",
                inputs={
                    bus_set.ac: solph.Flow(variable_costs=0.0),
                },
                outputs={
                    bus_set.thermal.cooling: solph.Flow(
                        nominal_capacity=cop_arrays.cooling_capacity_kw,
                    ),
                },
                conversion_factors={
                    bus_set.thermal.cooling: solph.sequence(cop_arrays.cooling),
                },
            )
            nodes.append(hp_cooler)
            log.debug(
                "HP cooler: AC -> cool_bus, rated=%.1f kW_th, mean_COP_c=%.2f, max_COP_c=%.2f",
                cop_arrays.cooling_capacity_kw,
                float(np.mean(cop_arrays.cooling)),
                float(np.max(cop_arrays.cooling)),
            )

        # ------------------------------------------------------------------
        # Standby / parasitic draw (optional)
        # ------------------------------------------------------------------
        if hp.standby_power_kw > 0.0:
            hp_standby: Any = solph.components.Sink(
                label="hp_standby",
                inputs={
                    bus_set.ac: solph.Flow(
                        fix=np.ones(n_timesteps),
                        nominal_capacity=hp.standby_power_kw,
                    ),
                },
            )
            nodes.append(hp_standby)
            log.debug("HP standby sink: %.3f kW on AC bus", hp.standby_power_kw)

        log.info(
            "HeatPumpBuilder: built %d node(s) for model %s (%d BTU/hr), mode=%s",
            len(nodes),
            cop_arrays.model_name,
            cop_arrays.model_btu,
            mode,
        )
        return nodes
