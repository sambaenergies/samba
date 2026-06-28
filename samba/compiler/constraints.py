# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Hard constraint injection for oemof-solph models.

This module is called from Phase 5's ''solve()'' function **after**
''model = solph.Model(energy_system)'' has been created and **before**
''model.solve()'' is called.

Constraint mapping
------------------
Every field in :class:'~samba.scenario.models.Constraints' maps to a hard
model constraint here (or to a post-solve check documented below):

+--------------------------------+---------------------------------------+--------+
| Schema field                   | Implementation                        | Phase  |
+================================+=======================================+========+
| ''force_grid_disconnect''      | Compiler guard (no Grid nodes added)  | 4      |
+--------------------------------+---------------------------------------+--------+
| ''min_renewable_fraction''     | Pyomo ''Constraint'' on model         | 4/5    |
+--------------------------------+---------------------------------------+--------+
| ''budget''                     | Pyomo ''Constraint'' on invest vars   | 4/5    |
+--------------------------------+---------------------------------------+--------+
| ''max_lpsp''                   | Post-solve check (Phase 5)            | 5      |
+--------------------------------+---------------------------------------+--------+
| ''max_annual_diesel_l''        | Post-solve check (Phase 6)            | 6      |
+--------------------------------+---------------------------------------+--------+
| ''max_battery_cycles_yr''      | Post-solve check (Phase 6)            | 6      |
+--------------------------------+---------------------------------------+--------+
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import oemof.solph as solph

    from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["ConstraintViolationError", "inject_hard_constraints"]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConstraintViolationError(Exception):
    """Raised when a post-solve or post-process hard constraint is violated.

    Attributes
    ----------
    field:
        The Scenario constraints field name that was violated.
    value:
        The computed value from the solve results.
    limit:
        The allowed limit defined in the scenario.
    deviation:
        ''value - limit'' (positive means over-limit).
    """

    def __init__(
        self,
        field: str,
        value: float,
        limit: float,
        deviation: float,
        message: str = "",
    ) -> None:
        self.field = field
        self.value = value
        self.limit = limit
        self.deviation = deviation
        msg = message or (
            f"Constraint violated: {field}={value:.6g} exceeds limit {limit:.6g} "
            f"(deviation={deviation:+.6g})"
        )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Constraint injector
# ---------------------------------------------------------------------------


def inject_hard_constraints(
    model: solph.Model,
    scenario: Scenario,
    energy_system: solph.EnergySystem,
) -> None:
    """Add hard Pyomo constraints to *model* before calling ''model.solve()''.

    This function is a no-op for constraints that are either:
    - Already enforced at compile time (e.g. ''force_grid_disconnect''), or
    - Post-solve checks handled elsewhere (e.g. ''max_lpsp'', ''max_annual_diesel_l'').

    Parameters
    ----------
    model:
        The ''solph.Model'' (Pyomo ''ConcreteModel'') built from *energy_system*.
    scenario:
        Validated scenario -- constraint parameters are read from
        ''scenario.constraints''.
    energy_system:
        The ''solph.EnergySystem'' that was compiled; used to look up node
        references when building Pyomo expressions.

    Notes
    -----
    Pyomo constraints are added via ''model.add_component(name, constraint_obj)''.
    The oemof-solph flow variable block is ''model.flow'' with keys
    ''(source_node, target_node, period, timestep)''.
    """
    constraints = scenario.constraints

    if constraints.min_renewable_fraction > 0.0:
        _inject_min_renewable_fraction(model, scenario, energy_system)

    if scenario.project.budget is not None:
        _inject_budget_constraint(model, scenario, energy_system)

    demand_charge = getattr(scenario.tariff, "demand_charge", None)
    if demand_charge is not None and demand_charge.rate_per_kw_month > 0.0:
        _inject_demand_charge(model, scenario, energy_system)

    if constraints.max_total_emissions_kg is not None:
        _inject_max_emissions(model, scenario, energy_system)


# ---------------------------------------------------------------------------
# Individual constraint builders
# ---------------------------------------------------------------------------


def _inject_min_renewable_fraction(
    model: solph.Model,
    scenario: Scenario,
    energy_system: solph.EnergySystem,
) -> None:
    """Add a Pyomo constraint enforcing minimum renewable energy fraction.

    Constraint
    ----------
    .. math::

       \\eta_{inv} \\cdot \\sum_{t} (P_{PV,t}^{DC} + P_{WT,t}^{DC})
       \\geq f_{RE} \\cdot \\sum_{t} P_{load,t}

    Both PV and wind are DC-coupled sources, so renewable generation is
    ''P_RE = Ppv + Pwt''.  Multiplying DC generation by :math:'\\eta_{inv}'
    converts to AC-equivalent kWh, ensuring the constraint is on the same unit
    basis as the AC load: ''RE = (Ppv + Pwt) x eta / load_AC''.

    where :math:'f_{RE}' = ''scenario.constraints.min_renewable_fraction''.

    Implementation note (Phase 5)
    ------------------------------
    oemof-solph stores dispatch flows in ''model.flow'', keyed by
    ''(source_node, target_bus, t)''.  Nodes are retrieved from
    ''energy_system.groups'' by label.  This implementation relies on
    the label conventions set in each builder:

    - PV source label: ''"pv"''
    - DC bus label: ''"dc_bus"''
    - Wind turbine source label: ''"wind_turbine"'' (DC-coupled, output on dc_bus)
    - AC bus label: ''"ac_bus"''
    - Load sink label: ''"load"''
    """
    import pyomo.environ as pyo

    frac = scenario.constraints.min_renewable_fraction
    groups = energy_system.groups  # dict label -> Node

    dc_bus = groups.get("dc_bus")
    ac_bus = groups.get("ac_bus")
    pv_node = groups.get("pv")
    wt_node = groups.get("wind_turbine")
    load_node = groups.get("load")

    if load_node is None or ac_bus is None:
        log.warning("Cannot inject min_renewable_fraction: load or ac_bus not found in groups")
        return

    # Inverter efficiency for DC->AC unit conversion (RE = (Ppv+Pwt)xeta/load).
    # comps.inverter is always present (required field in Components).
    eta_inv: float = scenario.components.inverter.efficiency

    def _renewable_fraction_rule(m: Any) -> Any:
        # Sum all timestep indices
        T = list(m.TIMESTEPS)

        # Wind is DC-coupled (dc_bus) after Bug C fix.  Scale both PV and wind
        # DC flows by eta_inv to express them in AC-equivalent kWh so the
        # constraint is on the same basis as the AC load.
        renewable_sum = eta_inv * (
            pyo.quicksum(
                m.flow[pv_node, dc_bus, t] for t in T if pv_node is not None and dc_bus is not None
            )
            + pyo.quicksum(
                m.flow[wt_node, dc_bus, t] for t in T if wt_node is not None and dc_bus is not None
            )
        )

        load_sum = pyo.quicksum(m.flow[ac_bus, load_node, t] for t in T)

        return renewable_sum >= frac * load_sum

    model.add_component(
        "samba_min_renewable_fraction",
        pyo.Constraint(rule=_renewable_fraction_rule),
    )
    log.info("Injected min_renewable_fraction constraint (>= %.1f%%)", frac * 100)


def _inject_demand_charge(
    model: solph.Model,
    scenario: Scenario,
    energy_system: solph.EnergySystem,
) -> None:
    """Add a monthly-peak demand charge to the LP (v4).

    For each calendar month *m*, a non-negative peak variable ``peak[m]`` is
    constrained to be >= the grid import at every (eligible) timestep in that
    month, and ``rate_per_kw_month x Σ_m peak[m]`` is added to the objective.
    Because the peak enters the objective, the solver has an incentive to shave
    it (e.g. by discharging storage) rather than merely being billed for it.

    The objective term is in the same annual-cost basis as oemof's
    ``variable_costs`` (one representative year); the economics layer applies the
    present-worth factor in post-processing (see ``economics.cashflow._grid_costs``).
    """
    import pyomo.environ as pyo

    from samba.tariff.demand import hour_month_index

    dc = scenario.tariff.demand_charge
    if dc is None or dc.rate_per_kw_month <= 0.0:
        return

    groups = energy_system.groups
    grid_import = groups.get("grid_import")
    ac_bus = groups.get("ac_bus")
    if grid_import is None or ac_bus is None:
        log.warning("Cannot inject demand_charge: grid_import or ac_bus not found in groups")
        return

    n_ts = len(list(model.TIMESTEPS))
    months = hour_month_index()  # (8760,) month index 0-11 per hour-of-year
    allowed_hours = set(dc.hours) if dc.hours is not None else None

    model.add_component("samba_demand_peak", pyo.Var(range(12), domain=pyo.NonNegativeReals))
    peak_var = model.samba_demand_peak

    def _peak_rule(m: Any, t: int) -> Any:
        if t >= n_ts or t >= months.shape[0]:
            return pyo.Constraint.Skip
        if allowed_hours is not None and (t % 24) not in allowed_hours:
            return pyo.Constraint.Skip
        month_idx = int(months[t])
        return peak_var[month_idx] >= m.flow[grid_import, ac_bus, t]

    model.add_component(
        "samba_demand_peak_con",
        pyo.Constraint(model.TIMESTEPS, rule=_peak_rule),
    )

    rate = dc.rate_per_kw_month
    model.objective.expr += rate * pyo.quicksum(peak_var[m] for m in range(12))
    log.info("Injected demand charge: %.2f $/kW-month (LP peak-shaving)", rate)


def _inject_max_emissions(
    model: solph.Model,
    scenario: Scenario,
    energy_system: solph.EnergySystem,
) -> None:
    """Cap annual CO2 at ``constraints.max_total_emissions_kg`` (epsilon-constraint, v4).

    Constraint
    ----------
    .. math::

       f_{grid} \\cdot \\sum_t P_{grid,t}
       + (\\sigma_{DG} \\cdot \\gamma_{DG}) \\cdot \\sum_t P_{DG,t}
       \\leq \\varepsilon

    where :math:`f_{grid}` = ``grid.emission_factor_kg_per_kwh``,
    :math:`\\sigma_{DG}` = ``diesel.slope_l_per_kwh`` and
    :math:`\\gamma_{DG}` = ``diesel.co2_per_liter_kg``.  This mirrors the
    LP-expressible part of ``total_emissions_kg`` (the no-load fuel *intercept*
    is post-processed only, exactly as for fuel cost).  Driving :math:`\\varepsilon`
    across a range traces the **true** Pareto frontier, including non-convex
    regions the weighted-sum method misses.
    """
    import pyomo.environ as pyo

    epsilon = scenario.constraints.max_total_emissions_kg
    if epsilon is None:
        return

    groups = energy_system.groups
    ac_bus = groups.get("ac_bus")
    grid_import = groups.get("grid_import")
    diesel = groups.get("diesel_generator")
    comps = scenario.components

    grid_factor = 0.0
    if grid_import is not None and comps.grid is not None:
        grid_factor = float(comps.grid.emission_factor_kg_per_kwh)

    dg_factor = 0.0
    if diesel is not None and comps.diesel_generator is not None:
        dg = comps.diesel_generator
        dg_factor = float(dg.slope_l_per_kwh) * float(dg.co2_per_liter_kg)

    if ac_bus is None or (grid_factor == 0.0 and dg_factor == 0.0):
        log.warning("Cannot inject max_total_emissions_kg: no emitting source found; skipping")
        return

    def _emissions_rule(m: Any) -> Any:
        T = list(m.TIMESTEPS)
        terms = []
        if grid_import is not None and grid_factor > 0.0:
            terms.append(grid_factor * pyo.quicksum(m.flow[grid_import, ac_bus, t] for t in T))
        if diesel is not None and dg_factor > 0.0:
            terms.append(dg_factor * pyo.quicksum(m.flow[diesel, ac_bus, t] for t in T))
        return pyo.quicksum(terms) <= epsilon

    model.add_component("samba_max_emissions", pyo.Constraint(rule=_emissions_rule))
    log.info("Injected max_total_emissions_kg constraint (<= %.2f kg)", epsilon)


def _inject_budget_constraint(
    model: solph.Model,
    scenario: Scenario,
    energy_system: solph.EnergySystem,
) -> None:
    """Add a Pyomo constraint enforcing the capital budget limit.

    Constraint
    ----------
    .. math::

       \\sum_{i} \\hat{C}_i \\cdot x_i \\leq B

    where :math:'\\hat{C}_i' is the unit capital cost ($/kW or $/kWh) of
    component *i*, :math:'x_i' is the oemof Investment variable (kW or kWh),
    and :math:'B' is ''scenario.project.budget''.

    The budget is expressed in **total capital cost** (same currency as the
    ''capex_per_kw'' / ''capex_per_kwh'' fields in the scenario).

    Implementation note
    -------------------
    Investment variables for flows are in ''model.InvestmentFlowBlock.invest''
    keyed by ''(source_node, target_node, period_idx)''.

    Investment variables for storage are in
    ''model.GenericInvestmentStorageBlock.invest''
    keyed by ''(storage_node, period_idx)''.

    We build a *capex map* directly from ''scenario.components'' and
    ''energy_system.groups'' so we can look up the correct $/unit value for
    each Pyomo variable.
    """
    import pyomo.environ as pyo

    budget = scenario.project.budget
    if budget is None:
        return

    # ------------------------------------------------------------------
    # Build capex maps from scenario component definitions
    #   capex_flow_map:    (src_node, tgt_node) -> capex_$/kW
    #   capex_storage_map:  storage_node        -> capex_$/kWh
    # ------------------------------------------------------------------
    groups = energy_system.groups
    comps = scenario.components

    capex_flow_map: dict[tuple[Any, Any], float] = {}
    capex_storage_map: dict[Any, float] = {}

    if comps.pv is not None and comps.pv.enabled and comps.pv.capacity_kw is None:
        pv_node = groups.get("pv")
        dc_bus = groups.get("dc_bus")
        if pv_node is not None and dc_bus is not None:
            capex_flow_map[(pv_node, dc_bus)] = comps.pv.capex_per_kw

    if comps.battery is not None and comps.battery.enabled and comps.battery.capacity_kwh is None:
        batt_node = groups.get("battery")
        if batt_node is not None:
            capex_storage_map[batt_node] = comps.battery.capex_per_kwh

    if comps.inverter is not None and comps.inverter.capacity_kw is None:
        inv_node = groups.get("inverter")
        ac_bus = groups.get("ac_bus")
        if inv_node is not None and ac_bus is not None:
            capex_flow_map[(inv_node, ac_bus)] = comps.inverter.capex_per_kw

    def _budget_rule(m: Any) -> Any:
        terms: list[Any] = []

        # --- Flow investment variables ---
        invest_block = getattr(m, "InvestmentFlowBlock", None)
        if invest_block is not None:
            for (i, o, _p), var in invest_block.invest.items():
                cost = capex_flow_map.get((i, o), 0.0)
                if cost > 0.0:
                    terms.append(cost * var)

        # --- Storage investment variables ---
        storage_block = getattr(m, "GenericInvestmentStorageBlock", None)
        if storage_block is not None:
            for (n, _p), var in storage_block.invest.items():
                cost = capex_storage_map.get(n, 0.0)
                if cost > 0.0:
                    terms.append(cost * var)

        if not terms:
            log.warning(
                "Budget constraint: no investment variables with known capex found; skipping"
            )
            return pyo.Constraint.Skip

        return pyo.quicksum(terms) <= budget

    model.add_component(
        "samba_budget",
        pyo.Constraint(rule=_budget_rule),
    )
    log.info("Injected budget constraint (<= %.2f)", budget)
