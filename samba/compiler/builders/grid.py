# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Grid connection builder for oemof-solph.

Creates a grid import ''Source'' and, optionally, a grid export ''Sink'' on
the AC bus.  Time-varying electricity prices are passed as 8 760-element
''variable_costs'' arrays.

oemof sign convention
---------------------
In oemof, ''variable_costs'' on a ''Sink'' must be **negative** to represent
revenue (negative cost = income).  The compiler therefore passes ''-csell''
as the variable_costs on the export sink.
"""

from __future__ import annotations

import logging

import numpy as np
import oemof.solph as solph

from samba.economics.emissions import calc_grid_co2_var_cost
from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["GridBuilder"]


class GridBuilder:
    """Builds the oemof grid import source (and optional export sink)."""

    def build(
        self,
        scenario: Scenario,
        dc_bus: solph.Bus,
        ac_bus: solph.Bus,
        cbuy: np.ndarray,
        csell: np.ndarray,
        alpha: float = 0.0,
    ) -> list[solph.network.Node]:
        """Return ''[grid_import]'' or ''[grid_import, grid_export]''.

        Parameters
        ----------
        scenario:
            Validated scenario; ''scenario.components.grid'' must not be ''None''.
        dc_bus:
            DC system bus (unused; accepted for protocol compatibility).
        ac_bus:
            AC system bus.
        cbuy:
            8 760-element array of hourly grid purchase prices [$/kWh].
        csell:
            8 760-element array of hourly grid sell prices [$/kWh].
            Only used when ''scenario.components.grid.export_allowed'' is ''True''.
        alpha:
            Carbon price [$/kg CO2].  When > 0 and
            ''grid.emission_factor_kg_per_kwh > 0'', the CO2 cost is added
            to every element of *cbuy* so the solver penalises grid imports.

        Returns
        -------
        list of one or two :class:'solph.network.Node' objects.
        """
        grid = scenario.components.grid
        if grid is None:
            raise ValueError("GridBuilder.build called but scenario.components.grid is None")

        # Optionally inflate buy prices with a CO2 variable cost.
        effective_cbuy = cbuy.copy()
        if alpha > 0.0 and grid.emission_factor_kg_per_kwh > 0.0:
            co2_adder = calc_grid_co2_var_cost(grid.emission_factor_kg_per_kwh, alpha)
            effective_cbuy = cbuy + co2_adder
            log.debug("Grid: CO2 adder=%.4f $/kWh (alpha=%.4f)", co2_adder, alpha)

        # Grid import: buy electricity at time-varying rates
        grid_import: solph.network.Node = solph.components.Source(
            label="grid_import",
            outputs={
                ac_bus: solph.Flow(
                    nominal_capacity=grid.capacity_kw,
                    variable_costs=effective_cbuy,
                )
            },
        )
        log.debug("Grid: import capacity=%.2f kW", grid.capacity_kw)

        nodes: list[solph.network.Node] = [grid_import]

        if grid.export_allowed:
            # Grid export: sell electricity at time-varying rates (negative cost = revenue)
            grid_export: solph.network.Node = solph.components.Sink(
                label="grid_export",
                inputs={
                    ac_bus: solph.Flow(
                        nominal_capacity=grid.export_capacity_kw,
                        variable_costs=-csell,
                    )
                },
            )
            log.debug("Grid: export allowed, capacity=%.2f kW", grid.export_capacity_kw)
            nodes.append(grid_export)

        return nodes
