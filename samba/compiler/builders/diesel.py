# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Diesel generator builder for oemof-solph.

Implements the correct oemof topology for a diesel generator:

    [fuel_source] -> fuel_bus -> [diesel_generator_converter] -> ac_bus

A direct ''Source'' on the AC bus cannot model the fuel-to-electricity
conversion ratio or expose fuel consumption as a flow variable for
post-processing.  The ''Converter'' approach is required.

Fuel cost accounting
--------------------
The diesel consumption model is the standard linear fuel curve (e.g. HOMER
Pro), an affine function of output power:

    fuel [L/h] = slope [L/kWh] x P [kW] + intercept [L/kW*h] x P_rated [kW]

The **slope** component is captured as the ''variable_costs'' on the
''fuel_source'' (cost per kWh of electrical output = slope x fuel_price).
The **intercept** term represents a fixed cost per *operating hour* that
depends on whether the generator is on; it is tracked in post-processing
(Phase 6) to avoid introducing bi-linear terms into the LP.

Unit commitment (MILP)
----------------------
When any of ''min_up_hours'', ''min_down_hours'', or ''startup_cost'' are
non-zero (or when ''min_load_fraction > 0''), the builder attaches an oemof
:class:'NonConvex' object to the converter output flow.  This introduces
binary on/off variables and converts the problem to a MILP.  Setting all
three to their defaults (0, 0, 0.0) produces a pure LP identical to v1
behaviour.
"""

from __future__ import annotations

import logging

import oemof.solph as solph
from oemof.solph import NonConvex

from samba.compiler.annualize import ep_costs as _ep_costs
from samba.economics.emissions import calc_diesel_co2_var_cost
from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["DieselBuilder"]


class DieselBuilder:
    """Builds the oemof diesel generator node group on the AC bus."""

    def build(
        self,
        scenario: Scenario,
        dc_bus: solph.Bus,
        ac_bus: solph.Bus,
        alpha: float = 0.0,
    ) -> list[solph.network.Node]:
        """Return ''[fuel_bus, fuel_source, diesel_converter]''.

        Parameters
        ----------
        scenario:
            Validated scenario; ''scenario.components.diesel_generator'' must
            not be ''None''.
        dc_bus:
            DC system bus (unused; accepted for protocol compatibility).
        ac_bus:
            AC system bus where the generator delivers electricity.
        alpha:
            Carbon price [$/kg CO2] from ''scenario.objective.emissions_weight''.
            When > 0, a CO2 variable cost is added to the fuel source so the
            solver penalises diesel generation proportionally to its emissions.

        Returns
        -------
        list of three :class:'solph.network.Node' objects:
            ''fuel_bus'', ''fuel_source'', ''diesel_generator'' converter.

        Notes
        -----
        **MILP mode** is activated when any of the unit-commitment fields are
        non-zero (''min_up_hours'', ''min_down_hours'', ''startup_cost'') or
        when ''min_load_fraction > 0''.  In MILP mode a :class:'NonConvex'
        object is attached to the output flow, introducing binary on/off
        variables.  With all fields at their defaults the build is a pure LP.
        """
        dg = scenario.components.diesel_generator
        if dg is None:
            raise ValueError(
                "DieselBuilder.build called but scenario.components.diesel_generator is None"
            )

        proj = scenario.project

        # ------------------------------------------------------------------
        # Fuel cost per kWh of electrical output:
        #   slope_l_per_kwh x fuel_price_per_l  [$/kWh_e]
        # Plus CO2 variable cost when alpha > 0:
        #   co2_per_liter_kg x slope_l_per_kwh x alpha  [$/kWh_e]
        # The intercept is handled in post-processing (not in LP).
        # ------------------------------------------------------------------
        fuel_cost_per_kwh_e = dg.slope_l_per_kwh * dg.fuel_price_per_l
        if alpha > 0.0:
            fuel_cost_per_kwh_e += calc_diesel_co2_var_cost(
                dg.co2_per_liter_kg, dg.slope_l_per_kwh, alpha
            )

        # ------------------------------------------------------------------
        # Unit-commitment: determine whether MILP mode is needed.
        # Any non-zero value triggers NonConvex (binary on/off variables).
        # ------------------------------------------------------------------
        milp_mode = (
            dg.min_up_hours > 0
            or dg.min_down_hours > 0
            or dg.startup_cost > 0.0
            or dg.min_load_fraction > 0.0
        )

        log.debug(
            "Diesel: %.2f kW fixed, fuel_cost=%.4f $/kWh_e, MILP mode=%s "
            "(min_up=%d, min_down=%d, startup_cost=%.2f)",
            dg.capacity_kw,
            fuel_cost_per_kwh_e,
            milp_mode,
            dg.min_up_hours,
            dg.min_down_hours,
            dg.startup_cost,
        )

        # 1. Internal fuel bus (unitless; one kWh fuel -> one kWh electricity)
        fuel_bus: solph.network.Node = solph.Bus(label="diesel_fuel_bus")

        # 2. Fuel source: variable_costs represent $/kWh of electrical output
        fuel_source: solph.network.Node = solph.components.Source(
            label="diesel_fuel_source",
            outputs={
                fuel_bus: solph.Flow(variable_costs=fuel_cost_per_kwh_e),
            },
        )

        # 3. Converter output flow -- LP or MILP depending on milp_mode
        if milp_mode:
            non_convex = NonConvex(
                minimum_uptime=dg.min_up_hours,
                minimum_downtime=dg.min_down_hours,
                startup_costs=dg.startup_cost,
            )
            output_flow = solph.Flow(
                nominal_capacity=dg.capacity_kw,
                minimum=dg.min_load_fraction,
                nonconvex=non_convex,
            )
        else:
            # Pure LP: no NonConvex, no binary variables
            output_flow = solph.Flow(nominal_capacity=dg.capacity_kw)

        # 4. Converter: fuel_bus -> ac_bus
        diesel_gen: solph.network.Node = solph.components.Converter(
            label="diesel_generator",
            inputs={fuel_bus: solph.Flow()},
            outputs={ac_bus: output_flow},
            conversion_factors={fuel_bus: 1.0, ac_bus: 1.0},
        )

        # Annual capex for economics post-processing (logged, not in LP)
        annual_capex = _ep_costs(
            dg.capex_per_kw * dg.capacity_kw, proj.discount_rate_nominal, dg.lifetime_years
        )
        log.debug("Diesel: annualized capex=%.2f $/yr (post-process only)", annual_capex)

        return [fuel_bus, fuel_source, diesel_gen]
