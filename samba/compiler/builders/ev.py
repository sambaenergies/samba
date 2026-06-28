# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""EV / V2G component builder for oemof-solph.

Topology
--------
oemof-solph ''GenericStorage'' only allows **one** input flow and **one**
output flow.  To support simultaneous travel depletion, V2G discharge, and
smart charging while meeting this constraint, the EV subsystem uses a
dedicated internal **EV bus** (''ev_bus'')::

    ac_bus -> [ev_charger] -> ev_bus <-> [ev_storage]
                                |
                          [ev_travel sink]     (if travel depletion > 0)
    ac_bus <- [ev_v2g]  <- ev_bus              (if v2g_enabled)

Specifically:
* ''ev_bus''     -- dedicated internal bus for the EV subsystem
* ''ev_charger'' -- Converter: AC bus -> EV bus, presence-gated
* ''ev_storage'' -- GenericStorage: single input *and* single output on EV bus
* ''ev_travel''  -- Sink: fixed drain at departure hours (travel depletion)
* ''ev_v2g''     -- Converter: EV bus -> AC bus (only when ''v2g_enabled=True'')

Efficiencies are modeled on the storage (''inflow_conversion_factor'' and
''outflow_conversion_factor''); the converters are lossless (efficiency=1).

Travel depletion:
* ''ev_travel'' is a Sink with ''fix'' forcing consumption of
  ''(soc_departure - soc_arrival) x capacity_kwh'' kWh at each departure
  hour.  This implicitly enforces the departure SOC: if the storage does not
  hold enough energy, the LP is infeasible (correct physical behaviour).
* Omitted when ''soc_departure == soc_arrival'' or there are no departures.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import oemof.solph as solph
import pandas as pd

from samba.load_profiles.ev_presence import find_departure_hours

if TYPE_CHECKING:
    from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["EVBuilder"]


class EVBuilder:
    """Builds oemof nodes for the EV / V2G component."""

    def build(
        self,
        scenario: Scenario,
        ac_bus: solph.Bus,
        presence: np.ndarray,
        csell: np.ndarray | None,
        timeindex: pd.DatetimeIndex,
    ) -> list[solph.network.Node]:
        """Return the list of oemof nodes for the EV component.

        Parameters
        ----------
        scenario:
            Validated scenario; ''scenario.components.ev'' must not be ''None''.
        ac_bus:
            AC system bus -- EV charges from here and (if V2G) discharges here.
        presence:
            ''(8760,)'' float array, 1.0 = home/plugged-in, 0.0 = away.
        csell:
            ''(8760,)'' sell-tariff array [$/kWh].  Negative variable costs on
            the V2G discharge flow.  Pass ''None'' when V2G is disabled.
        timeindex:
            ''pd.DatetimeIndex'' of length 8760 matching the energy system.

        Returns
        -------
        list[solph.network.Node]
            Always: ''ev_bus'', ''ev_storage'', ''ev_charger''.
            Plus ''ev_travel'' when depletion > 0, ''ev_v2g'' when V2G enabled.
        """
        ev = scenario.components.ev
        if ev is None:
            raise ValueError("EVBuilder.build called but scenario.components.ev is None")

        # ------------------------------------------------------------------
        # Internal EV bus
        # ------------------------------------------------------------------
        ev_bus = solph.Bus(label="ev_bus")

        # ------------------------------------------------------------------
        # Travel depletion: fixed drain at each departure hour
        # ------------------------------------------------------------------
        departure_hrs = find_departure_hours(presence)
        depletion_energy = float((ev.soc_departure - ev.soc_arrival) * ev.capacity_kwh)
        has_travel = len(departure_hrs) > 0 and depletion_energy > 1e-9

        if has_travel:
            dep_kw = np.zeros(8760, dtype=np.float64)
            dep_kw[departure_hrs] = depletion_energy
            dep_norm = dep_kw / depletion_energy  # binary 0/1 array

            ev_travel: solph.network.Node | None = solph.components.Sink(
                label="ev_travel",
                inputs={
                    ev_bus: solph.Flow(
                        fix=pd.Series(dep_norm, index=timeindex),
                        nominal_capacity=depletion_energy,
                    )
                },
            )
            log.debug(
                "EV: travel depletion %.2f kWh/trip; %d departure events",
                depletion_energy,
                len(departure_hrs),
            )
        else:
            ev_travel = None
            log.debug("EV: no travel depletion (no departures or soc_dep == soc_arr)")

        # ------------------------------------------------------------------
        # EV charger: AC bus -> EV bus (presence-gated)
        # ------------------------------------------------------------------
        ev_charger = solph.components.Converter(
            label="ev_charger",
            inputs={ac_bus: solph.Flow(nominal_capacity=ev.max_charge_kw, maximum=presence)},
            outputs={ev_bus: solph.Flow(nominal_capacity=ev.max_charge_kw)},
        )

        # ------------------------------------------------------------------
        # EV storage (single input + single output both on ev_bus)
        # ------------------------------------------------------------------
        discharge_nominal = max(
            depletion_energy if has_travel else 0.0,
            ev.max_discharge_kw if ev.v2g_enabled else 0.0,
            ev.max_charge_kw,  # fallback floor so storage can always recirculate
        )
        ev_storage = solph.components.GenericStorage(
            label="ev_storage",
            inputs={ev_bus: solph.Flow(nominal_capacity=ev.max_charge_kw)},
            outputs={ev_bus: solph.Flow(nominal_capacity=discharge_nominal)},
            nominal_capacity=ev.capacity_kwh,
            inflow_conversion_factor=ev.charge_efficiency,
            outflow_conversion_factor=ev.discharge_efficiency,
            min_storage_level=ev.soc_min,
            max_storage_level=ev.soc_max,
            initial_storage_level=ev.soc_initial,
            loss_rate=ev.self_discharge_rate,
        )
        log.debug(
            "EV: %.2f kWh storage, %.2f kW charger, discharge_nominal=%.2f kW, V2G=%s",
            ev.capacity_kwh,
            ev.max_charge_kw,
            discharge_nominal,
            ev.v2g_enabled,
        )

        # ------------------------------------------------------------------
        # V2G converter: EV bus -> AC bus (presence-gated, earns revenue)
        # ------------------------------------------------------------------
        if ev.v2g_enabled:
            sell = csell if csell is not None else np.zeros(8760, dtype=np.float64)
            ev_v2g: solph.network.Node | None = solph.components.Converter(
                label="ev_v2g",
                inputs={ev_bus: solph.Flow(nominal_capacity=ev.max_discharge_kw, maximum=presence)},
                outputs={
                    ac_bus: solph.Flow(
                        nominal_capacity=ev.max_discharge_kw,
                        variable_costs=-sell,
                    )
                },
            )
            log.debug("EV: V2G converter -- max_discharge_kw=%.2f", ev.max_discharge_kw)
        else:
            ev_v2g = None

        # ------------------------------------------------------------------
        # Assemble node list
        # ------------------------------------------------------------------
        nodes: list[solph.network.Node] = [ev_bus, ev_storage, ev_charger]
        if ev_travel is not None:
            nodes.append(ev_travel)
        if ev_v2g is not None:
            nodes.append(ev_v2g)

        return nodes
