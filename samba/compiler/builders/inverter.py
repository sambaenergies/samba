# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""DC/AC inverter builder for oemof-solph.

Creates a bidirectional ''solph.components.Converter'' linking the DC bus to
the AC bus.  The conversion factor accounts for inverter efficiency.

Investment mode (oemof-solph >= 0.6.1)
--------------------------------------
When building in Investment mode, **both** the input flow (DC bus) and the
output flow (AC bus) must carry an explicit ''solph.Investment()'' object.
The output flow carries the annualized ''ep_costs''; the input flow carries a
zero-cost ''Investment()'' whose capacity is linked to the output via
''invest_relation_input_output''.  This ensures the optimizer consistently
sizes the DC-side and AC-side capacities at the correct efficiency ratio.
"""

from __future__ import annotations

import logging

import oemof.solph as solph

from samba.compiler.annualize import ep_costs as _ep_costs
from samba.compiler.annualize import real_discount_rate as _real_rate
from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["InverterBuilder"]


class InverterBuilder:
    """Builds the oemof inverter converter node between DC and AC buses."""

    def build(
        self,
        scenario: Scenario,
        dc_bus: solph.Bus,
        ac_bus: solph.Bus,
    ) -> list[solph.network.Node]:
        """Return a single ''Converter'' linking *dc_bus* -> *ac_bus*.

        Parameters
        ----------
        scenario:
            Validated scenario; ''scenario.components.inverter'' must be set.
        dc_bus:
            DC system bus (inverter input).
        ac_bus:
            AC system bus (inverter output).

        Returns
        -------
        list containing one :class:'solph.components.Converter'
        """
        inv = scenario.components.inverter
        proj = scenario.project

        eff = inv.efficiency
        # For 1 kWh AC output -> 1/eff kWh DC input
        conv_factors = {dc_bus: 1.0 / eff, ac_bus: 1.0}

        if inv.capacity_kw is None:
            # ------- Investment mode -------
            r_real = _real_rate(proj.discount_rate_nominal, proj.inflation_rate)
            annual_cost = _ep_costs(inv.capex_per_kw, r_real, inv.lifetime_years)
            inverter: solph.network.Node = solph.components.Converter(
                label="inverter",
                inputs={
                    dc_bus: solph.Flow(
                        nominal_capacity=solph.Investment(),
                    )
                },
                outputs={
                    ac_bus: solph.Flow(
                        nominal_capacity=solph.Investment(ep_costs=annual_cost),
                    )
                },
                conversion_factors=conv_factors,
            )
            log.debug("Inverter: Investment mode -- ep_costs=%.4f $/kW/yr", annual_cost)
        else:
            # ------- Fixed capacity mode -------
            inverter = solph.components.Converter(
                label="inverter",
                inputs={dc_bus: solph.Flow()},
                outputs={ac_bus: solph.Flow(nominal_capacity=inv.capacity_kw)},
                conversion_factors=conv_factors,
            )
            log.debug("Inverter: Fixed mode -- capacity=%.2f kW", inv.capacity_kw)

        return [inverter]
