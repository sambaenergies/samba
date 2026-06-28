# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Gas supply component builder for Phase 23.

Creates two oemof nodes:

1. ``gas_supply`` -- :class:`oemof.solph.components.Source` on the gas bus
   carrying the hourly gas rate array as ``variable_costs``.
2. ``gas_boiler`` -- :class:`oemof.solph.components.Converter` from gas bus
   to heating bus, with ``conversion_factors={heat_bus: boiler_efficiency}``.

The **gas bus** is NOT created here -- it is pre-allocated by
:func:`~samba.thermal.buses.build_thermal_buses` and received via
``bus_set.thermal.gas``.  All bus creation is authoritative in
:mod:`samba.compiler.buses`.

oemof topology::

    [gas_supply Source] --gas_bus--> [gas_boiler Converter] --heat_bus--> demand
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np
import oemof.solph as solph

if TYPE_CHECKING:
    from samba.compiler.buses import BusSet
    from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["GasSupplyBuilder"]


class GasSupplyBuilder:
    """Build oemof gas supply nodes (Source + Converter)."""

    def build(
        self,
        scenario: Scenario,
        bus_set: BusSet,
        gas_rate_array: np.ndarray,
    ) -> list[solph.network.Node]:
        """Return ``[gas_supply, gas_boiler]`` for addition to the energy system.

        Parameters
        ----------
        scenario:
            Validated scenario (provides :class:`.GasSupply` configuration).
        bus_set:
            Compiled bus set.  Must have ``thermal.gas`` and ``thermal.heating``
            populated before this builder is called.
        gas_rate_array:
            Hourly gas purchase price [$/kWh_th], shape (8760,).  Built by
            :func:`~samba.tariff.gas.build_gas_rate_array`.

        Returns
        -------
        list of :class:`oemof.solph.network.Node`
            ``[gas_supply_source, gas_boiler_converter]`` (2 nodes).

        Raises
        ------
        ValueError
            If the gas bus or heating bus is missing from ``bus_set``.
        """
        if bus_set.thermal.gas is None:
            raise ValueError(
                "GasSupplyBuilder: gas bus is None -- ensure gas_supply is enabled "
                "so build_thermal_buses() creates the gas bus."
            )
        if bus_set.thermal.heating is None:
            raise ValueError(
                "GasSupplyBuilder: heating bus is None -- gas boiler requires a "
                "heating bus.  Enable heat_pump or ensure heat_pump wires the bus."
            )

        gs = scenario.components.gas_supply
        if gs is None:
            raise ValueError(
                "GasSupplyBuilder.build called but scenario.components.gas_supply is None"
            )

        gas_bus = bus_set.thermal.gas
        heat_bus = bus_set.thermal.heating

        # Emissions-adjusted variable cost (Phase 12 multi-objective support).
        emissions_adj = float(scenario.objective.emissions_weight) * gs.co2_per_kwh_th
        effective_rate: np.ndarray | float = (
            gas_rate_array + emissions_adj if emissions_adj > 0.0 else gas_rate_array
        )

        # --- Gas Source -------------------------------------------------------
        source_flow_kwargs: dict[str, Any] = {"variable_costs": effective_rate}
        if gs.max_output_kw_th is not None:
            # Cap the gas input flow at max_gas_kw = max_output_kw_th / efficiency.
            # This constrains the boiler thermal output without a separate
            # investment / capacity variable.
            max_gas_kw = gs.max_output_kw_th / gs.boiler_efficiency
            source_flow_kwargs["nominal_capacity"] = max_gas_kw

        gas_source = solph.components.Source(
            label="gas_supply",
            outputs={gas_bus: solph.Flow(**source_flow_kwargs)},
        )

        # --- Gas Boiler (Converter) -------------------------------------------
        gas_boiler = solph.components.Converter(
            label="gas_boiler",
            inputs={gas_bus: solph.Flow()},
            outputs={heat_bus: solph.Flow()},
            conversion_factors={heat_bus: gs.boiler_efficiency},
        )

        log.debug(
            "GasSupplyBuilder: gas_supply + gas_boiler "
            "(efficiency=%.2f, max_output_kw_th=%s, emissions_adj=%.4f $/kWh_th)",
            gs.boiler_efficiency,
            gs.max_output_kw_th,
            emissions_adj,
        )

        return [gas_source, gas_boiler]
