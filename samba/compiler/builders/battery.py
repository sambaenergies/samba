# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Battery energy storage builder for oemof-solph.

Creates a ''solph.components.GenericStorage'' on the DC bus.  In Investment
mode the optimizer determines the storage capacity (kWh); charge and discharge
power bounds are derived via ''invest_relation_*'' parameters.

API note (oemof-solph >= 0.6.1)
-------------------------------
When using ''invest_relation_input_capacity'' / ''invest_relation_output_capacity''
the input/output flows **must** each carry an explicit
''nominal_capacity=solph.Investment()'' (zero ep_costs).  The storage
''nominal_capacity'' carries the true annualized cost.  This is a hard
requirement in oemof >= 0.6.1 and replaces the old auto-create behaviour.
"""

from __future__ import annotations

import logging

import oemof.solph as solph

from samba.compiler.annualize import ep_costs as _ep_costs
from samba.compiler.annualize import real_discount_rate as _real_rate
from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["BatteryBuilder"]


class BatteryBuilder:
    """Builds the oemof GenericStorage node for the battery."""

    def build(
        self,
        scenario: Scenario,
        dc_bus: solph.Bus,
        ac_bus: solph.Bus,
    ) -> list[solph.network.Node]:
        """Return a single ''GenericStorage'' on *dc_bus*.

        Parameters
        ----------
        scenario:
            Validated scenario; ''scenario.components.battery'' must not be ''None''.
        dc_bus:
            DC system bus (both charge and discharge connect here).
        ac_bus:
            AC system bus (unused; accepted for protocol compatibility).

        Returns
        -------
        list containing one :class:'solph.components.GenericStorage'
        """
        bat = scenario.components.battery
        if bat is None:
            raise ValueError("BatteryBuilder.build called but scenario.components.battery is None")

        proj = scenario.project
        effective_capex = bat.capex_per_kwh * (1.0 - proj.re_incentive_rate)

        if bat.capacity_kwh is None:
            # ------- Investment mode -------
            r_real = _real_rate(proj.discount_rate_nominal, proj.inflation_rate)
            annual_cost = _ep_costs(effective_capex, r_real, bat.lifetime_years)
            batt: solph.network.Node = solph.components.GenericStorage(
                label="battery",
                inputs={
                    dc_bus: solph.Flow(nominal_capacity=solph.Investment()),
                },
                outputs={
                    dc_bus: solph.Flow(nominal_capacity=solph.Investment()),
                },
                nominal_capacity=solph.Investment(ep_costs=annual_cost),
                invest_relation_input_capacity=bat.c_rate_charge,
                invest_relation_output_capacity=bat.c_rate_discharge,
                inflow_conversion_factor=bat.charge_efficiency,
                outflow_conversion_factor=bat.discharge_efficiency,
                min_storage_level=bat.soc_min,
                max_storage_level=bat.soc_max,
                initial_storage_level=bat.soc_initial,
            )
            log.debug("Battery: Investment mode -- ep_costs=%.4f $/kWh/yr", annual_cost)
        else:
            # ------- Fixed capacity mode -------
            charge_kw = bat.capacity_kwh * bat.c_rate_charge
            discharge_kw = bat.capacity_kwh * bat.c_rate_discharge
            batt = solph.components.GenericStorage(
                label="battery",
                inputs={
                    dc_bus: solph.Flow(nominal_capacity=charge_kw),
                },
                outputs={
                    dc_bus: solph.Flow(nominal_capacity=discharge_kw),
                },
                nominal_capacity=bat.capacity_kwh,
                inflow_conversion_factor=bat.charge_efficiency,
                outflow_conversion_factor=bat.discharge_efficiency,
                min_storage_level=bat.soc_min,
                max_storage_level=bat.soc_max,
                initial_storage_level=bat.soc_initial,
            )
            log.debug("Battery: Fixed mode -- capacity=%.2f kWh", bat.capacity_kwh)

        return [batt]
