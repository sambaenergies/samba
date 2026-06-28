# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""PV array builder for oemof-solph.

Creates a ''solph.components.Source'' on the DC bus representing the PV array.
In Investment mode the optimizer chooses the installed kWp; in fixed mode the
capacity is set directly from ''scenario.components.pv.capacity_kw''.
"""

from __future__ import annotations

import logging

import numpy as np
import oemof.solph as solph

from samba.compiler.annualize import ep_costs as _ep_costs
from samba.compiler.annualize import real_discount_rate as _real_rate
from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["PVBuilder"]


class PVBuilder:
    """Builds the oemof PV source node(s) for the energy system."""

    def build(
        self,
        scenario: Scenario,
        dc_bus: solph.Bus,
        ac_bus: solph.Bus,
        pv_power_per_kwp: np.ndarray,
    ) -> list[solph.network.Node]:
        """Return a single ''Source'' representing the PV array on *dc_bus*.

        Parameters
        ----------
        scenario:
            Validated scenario; ''scenario.components.pv'' must not be ''None''.
        dc_bus:
            DC system bus.
        ac_bus:
            AC system bus (unused; accepted for protocol compatibility).
        pv_power_per_kwp:
            Normalised 8 760-element array of PV output fractions per kWp
            installed, in the range ''[0, 1]''.

        Returns
        -------
        list containing one :class:'solph.components.Source'
        """
        pv = scenario.components.pv
        if pv is None:
            raise ValueError("PVBuilder.build called but scenario.components.pv is None")

        proj = scenario.project
        # Re-investment incentive (e.g. 30 % ITC) reduces effective CAPEX.
        effective_capex_per_kw = pv.capex_per_kw * (1.0 - proj.re_incentive_rate)

        # Normalised profile clipped to [0, 1] (guards against numerical noise).
        profile = np.clip(pv_power_per_kwp, 0.0, 1.0)

        if pv.capacity_kw is None:
            # ------- Investment mode -------
            r_real = _real_rate(proj.discount_rate_nominal, proj.inflation_rate)
            annual_cost = _ep_costs(effective_capex_per_kw, r_real, pv.lifetime_years)
            flow = solph.Flow(
                fix=profile,
                nominal_capacity=solph.Investment(ep_costs=annual_cost),
            )
            log.debug("PV: Investment mode -- ep_costs=%.4f $/kWp/yr", annual_cost)
        else:
            # ------- Fixed capacity mode -------
            flow = solph.Flow(
                fix=profile,
                nominal_capacity=pv.capacity_kw,
            )
            log.debug("PV: Fixed mode -- capacity=%.2f kW", pv.capacity_kw)

        pv_source: solph.network.Node = solph.components.Source(
            label="pv",
            outputs={dc_bus: flow},
        )
        return [pv_source]
