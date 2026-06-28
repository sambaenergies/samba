# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""ThermalLoadBuilder -- Phase 22.

Replaces the zero-demand placeholder Sinks added in Phase 19 with real
demand Sinks driven by the :class:`~samba.load_profiles.thermal.ThermalLoads`
profile computed by :func:`~samba.load_profiles.thermal.load_thermal_loads`.

The penalty Sources (``heat_unmet`` / ``cool_unmet``) are **always** kept by
the compiler; this builder only produces real-demand Sink nodes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import oemof.solph as solph

from samba.load_profiles.thermal import ThermalLoads

if TYPE_CHECKING:
    from samba.compiler.buses import BusSet
    from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["ThermalLoadBuilder"]


class ThermalLoadBuilder:
    """Build thermal demand Sink nodes from a :class:`.ThermalLoads` profile."""

    def build(
        self,
        scenario: Scenario,
        bus_set: BusSet,
        thermal_loads: ThermalLoads,
    ) -> list[solph.network.Node]:
        """Return oemof Sink nodes for heating and/or cooling demand.

        One ``heat_load`` Sink is produced when the heating bus exists; one
        ``cool_load`` Sink when the cooling bus exists.  Profile arrays are
        normalised to ``fix ∈ [0, 1]`` with ``nominal_capacity = peak [kW_th]``
        following the same oemof pattern used for the electrical load sink.

        Parameters
        ----------
        scenario:
            Validated scenario (used for logging the constraint state).
        bus_set:
            Compiled bus set -- provides ``thermal.heating`` and
            ``thermal.cooling`` bus references.
        thermal_loads:
            Pre-computed hourly demand arrays [kW_th] from
            :func:`~samba.load_profiles.thermal.load_thermal_loads`.

        Returns
        -------
        list of :class:`oemof.solph.network.Node`
            Up to two Sink nodes: ``heat_load`` and/or ``cool_load``.

        Raises
        ------
        ValueError
            If cooling demand is non-zero but no cooling bus is configured.
        """
        # Validate cross-constraint: cooling demand with no cooling bus.
        if thermal_loads.cooling.sum() > 0.0 and not bus_set.thermal.has_cooling:
            _cool_kwh = thermal_loads.annual_cooling_kwh_th
            raise ValueError(
                "ThermalLoadBuilder: cooling demand is non-zero "
                f"(annual_cooling_kwh_th={_cool_kwh:.1f}) but no cooling bus "
                "is configured.  Add a cooling thermal bus or remove "
                "cooling_csv_path / reduce cooling setpoint."
            )

        nodes: list[solph.network.Node] = []

        # ---- Heating Sink ---------------------------------------------------
        if bus_set.thermal.has_heating:
            heating = thermal_loads.heating
            peak_h = float(heating.max())
            if peak_h > 0.0:
                profile_h = heating / peak_h
                nodes.append(
                    solph.components.Sink(
                        label="heat_load",
                        inputs={
                            bus_set.thermal.heating: solph.Flow(
                                fix=profile_h, nominal_capacity=peak_h
                            )
                        },
                    )
                )
            else:
                # Zero heating demand -- keep bus feasible with a zero Sink.
                nodes.append(
                    solph.components.Sink(
                        label="heat_load",
                        inputs={
                            bus_set.thermal.heating: solph.Flow(
                                fix=np.zeros(len(heating), dtype=float),
                                nominal_capacity=1.0,
                            )
                        },
                    )
                )
            log.debug(
                "ThermalLoadBuilder: heat_load Sink (peak=%.2f kW, annual=%.1f kWh_th)",
                peak_h,
                thermal_loads.annual_heating_kwh_th,
            )

        # ---- Cooling Sink ---------------------------------------------------
        if bus_set.thermal.has_cooling:
            cooling = thermal_loads.cooling
            peak_c = float(cooling.max())
            if peak_c > 0.0:
                profile_c = cooling / peak_c
                nodes.append(
                    solph.components.Sink(
                        label="cool_load",
                        inputs={
                            bus_set.thermal.cooling: solph.Flow(
                                fix=profile_c, nominal_capacity=peak_c
                            )
                        },
                    )
                )
            else:
                nodes.append(
                    solph.components.Sink(
                        label="cool_load",
                        inputs={
                            bus_set.thermal.cooling: solph.Flow(
                                fix=np.zeros(len(cooling), dtype=float),
                                nominal_capacity=1.0,
                            )
                        },
                    )
                )
            log.debug(
                "ThermalLoadBuilder: cool_load Sink (peak=%.2f kW, annual=%.1f kWh_th)",
                peak_c,
                thermal_loads.annual_cooling_kwh_th,
            )

        return nodes
