# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Endogenous piecewise-linear tiered tariff Pyomo injection (Phase 17).

This module implements the v2 endogenous tiered-tariff formulation.  When a
scenario uses a tiered buy tariff with ''endogenous_tiering=True'', the
compiler zeros out the grid import ''variable_costs'' and the solver runner
calls :func:'inject_tiered_cost' to add the correct PWL cost directly to the
Pyomo objective.

Mathematical formulation
------------------------
For each month *m* and tier *i*:

* :math:'M_m = \\sum_{t \\in \\text{month}_m} P_{\\text{grid}}[t] \\cdot \\Delta t'
* :math:'M_m = \\sum_i x_{m,i}', where :math:'x_{m,i} \\in [0, w_i]'
* :math:'\\text{cost}_m = \\sum_i r_i \\cdot x_{m,i}'

Because rates must be non-decreasing (:func:'validate_tier_specs' enforces
this), the LP fills cheaper lower tiers first without binary variables.

Supported tariff types
----------------------
''"tiered"'', ''"seasonal_tiered"'', ''"monthly_tiered"''
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from samba.scenario.models import BuyRate

log = logging.getLogger(__name__)

__all__ = [
    "TierSpec",
    "build_tier_specs",
    "validate_tier_specs",
    "month_hour_indices",
    "inject_tiered_cost",
]

_DAYS_IN_MONTH: list[int] = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# ---------------------------------------------------------------------------
# Precomputed month -> hour-index mapping (module-level, built once at import)
# ---------------------------------------------------------------------------


def _precompute_month_hours() -> dict[int, list[int]]:
    mapping: dict[int, list[int]] = {}
    h = 0
    for m, days in enumerate(_DAYS_IN_MONTH):
        mapping[m] = list(range(h, h + days * 24))
        h += days * 24
    return mapping


_MONTH_HOURS: dict[int, list[int]] = _precompute_month_hours()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class TierSpec:
    """Tier specification for a single calendar month.

    Attributes
    ----------
    month:
        0-based month index (0 = January, ..., 11 = December).
    boundaries:
        Upper consumption limit in kWh for each tier.  The last entry is
        ''float('inf')'' for the unlimited top tier.
    rates:
        Marginal price [$/kWh] for each tier.  Must have the same length as
        *boundaries*.  Must be non-decreasing (see :func:'validate_tier_specs').
    """

    month: int
    boundaries: list[float] = field(default_factory=list)
    rates: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def month_hour_indices(month: int) -> list[int]:
    """Return the 0-based hourly indices for *month* (0 = January).

    Uses a precomputed non-leap-year calendar (Jan=744 h, Feb=672 h, ...).

    Parameters
    ----------
    month:
        0-based month index in [0, 11].

    Returns
    -------
    list[int]
        Hour indices for that month, e.g. list(range(0, 744)) for January.

    Raises
    ------
    ValueError
        If *month* is outside [0, 11].
    """
    if not (0 <= month <= 11):
        raise ValueError(f"month must be in [0, 11], got {month!r}")
    return _MONTH_HOURS[month]


def build_tier_specs(buy: BuyRate) -> list[TierSpec]:
    """Build 12 :class:'TierSpec' objects from a tiered :class:'BuyRate'.

    Parameters
    ----------
    buy:
        A validated :class:'~samba.scenario.models.BuyRate' whose ''type'' is
        one of ''"tiered"'', ''"seasonal_tiered"'', or ''"monthly_tiered"''.

    Returns
    -------
    list[TierSpec]
        Exactly 12 :class:'TierSpec' objects, one per calendar month (January
        = index 0).

    Raises
    ------
    ValueError
        If the tariff type is not a supported tiered type.
    """
    specs: list[TierSpec] = []

    if buy.type == "tiered":
        if buy.tiers is None:
            raise ValueError("BuyRate.type='tiered' requires tiers to be set.")
        boundaries = [(t.limit_kwh if t.limit_kwh is not None else float("inf")) for t in buy.tiers]
        rates = [t.rate_per_kwh for t in buy.tiers]
        for m in range(12):
            specs.append(TierSpec(month=m, boundaries=list(boundaries), rates=list(rates)))

    elif buy.type == "monthly_tiered":
        if buy.monthly_tiers is None:
            raise ValueError("BuyRate.type='monthly_tiered' requires monthly_tiers to be set.")
        for m, tiers in enumerate(buy.monthly_tiers):
            boundaries = [(t.limit_kwh if t.limit_kwh is not None else float("inf")) for t in tiers]
            rates = [t.rate_per_kwh for t in tiers]
            specs.append(TierSpec(month=m, boundaries=boundaries, rates=rates))

    elif buy.type == "seasonal_tiered":
        if buy.seasonal_tiers is None:
            raise ValueError("BuyRate.type='seasonal_tiered' requires seasonal_tiers to be set.")
        # Build 1-based month -> tier list mapping (SeasonalTiers uses 1-based months)
        month_tiers: dict[int, Any] = {}
        for st in buy.seasonal_tiers:
            for m1 in st.months:
                month_tiers[m1] = st.tiers  # later entries override earlier ones

        for m in range(12):
            _season_tiers: Any = month_tiers.get(m + 1)  # 0-based -> 1-based lookup
            if _season_tiers is None:
                # Month not covered by any season -- zero-cost single unlimited tier
                specs.append(TierSpec(month=m, boundaries=[float("inf")], rates=[0.0]))
            else:
                boundaries = [
                    (t.limit_kwh if t.limit_kwh is not None else float("inf"))
                    for t in _season_tiers
                ]
                rates = [t.rate_per_kwh for t in _season_tiers]
                specs.append(TierSpec(month=m, boundaries=boundaries, rates=rates))

    else:
        raise ValueError(
            f"build_tier_specs called with unsupported tariff type {buy.type!r}. "
            "Only 'tiered', 'seasonal_tiered', and 'monthly_tiered' are supported."
        )

    return specs


def validate_tier_specs(specs: list[TierSpec]) -> None:
    """Raise :exc:'ValueError' if any month has decreasing tier rates.

    Non-decreasing rates are required for the LP endogenous formulation to be
    correct without binary variables.  Declining-block tariffs (cheaper higher
    tiers) must use ''endogenous_tiering=False'' (v1 pre-compute).

    Parameters
    ----------
    specs:
        List of :class:'TierSpec' objects to validate.

    Raises
    ------
    ValueError
        Descriptive message including the month index and tier pair where the
        rate decrease was detected.
    """
    for spec in specs:
        for i in range(1, len(spec.rates)):
            if spec.rates[i] < spec.rates[i - 1] - 1e-12:
                raise ValueError(
                    "Endogenous tiering requires non-decreasing tier rates. "
                    f"Found decreasing rate pair at month {spec.month} tier {i}: "
                    f"{spec.rates[i - 1]:.4f} -> {spec.rates[i]:.4f}. "
                    "Use endogenous_tiering=False for declining-block tariffs."
                )


def inject_tiered_cost(
    model: Any,
    energy_system: Any,
    tier_specs: list[TierSpec],
    dt_h: float = 1.0,
) -> None:
    """Inject monthly tiered-cost PWL constraints into the Pyomo *model*.

    This function is called from the solver runner **after**
    ''model = solph.Model(energy_system)'' and **before** ''model.solve()''.
    The compiler must have zeroed the grid import ''variable_costs'' so there
    is no double-counting.

    Added Pyomo components
    ----------------------
    * ''samba_monthly_consumption'' -- ''Var(range(12), NonNegativeReals)''
    * ''samba_monthly_consumption_def'' -- ''Constraint'' defining each as
      ''sum(flow[grid, ac_bus, t] * dt_h for t in month_hours)''
    * ''samba_tier_kwh'' -- ''Var((m,i), NonNegativeReals)''
    * ''samba_tier_ub'' -- upper-bound constraints (tier widths)
    * ''samba_tier_sum'' -- partition constraints (sum of x[m,i] == M_m)
    * Augments the active ''Objective'' with
      :math:'\\sum_{m,i} r_{m,i} \\cdot x_{m,i}'.

    Parameters
    ----------
    model:
        ''solph.Model'' (Pyomo ''ConcreteModel'') already built from
        *energy_system*.
    energy_system:
        ''solph.EnergySystem'' compiled by the compiler.  Used to look up
        ''"grid_import"'' and ''"ac_bus"'' node objects.
    tier_specs:
        12 :class:'TierSpec' objects (one per month), already validated by
        :func:'validate_tier_specs'.
    dt_h:
        Timestep duration in hours.  ''1.0'' for an 8760-hour annual model.
    """
    import pyomo.environ as pyo

    groups = energy_system.groups
    grid_node = groups.get("grid_import")
    ac_bus = groups.get("ac_bus")

    if grid_node is None or ac_bus is None:
        log.warning(
            "inject_tiered_cost: 'grid_import' or 'ac_bus' not found in energy_system.groups; "
            "skipping endogenous tariff injection"
        )
        return

    # ---------------------------------------------------------------
    # 1. Monthly consumption variables  M_m  [kWh]
    # ---------------------------------------------------------------
    model.add_component(
        "samba_monthly_consumption",
        pyo.Var(range(12), within=pyo.NonNegativeReals),
    )
    mc_var: Any = model.component("samba_monthly_consumption")

    # ---------------------------------------------------------------
    # 2. Define M_m = sum_t  flow[grid, ac_bus, t] * dt_h
    # ---------------------------------------------------------------
    def _monthly_def(_m: Any, m: int) -> Any:
        hours = _MONTH_HOURS[m]
        return mc_var[m] == pyo.quicksum(model.flow[grid_node, ac_bus, t] * dt_h for t in hours)

    model.add_component(
        "samba_monthly_consumption_def",
        pyo.Constraint(range(12), rule=_monthly_def),
    )

    # ---------------------------------------------------------------
    # 3. Tier decomposition variables  x[m, i]  [kWh]
    # ---------------------------------------------------------------
    tier_index = [(m, i) for m in range(12) for i in range(len(tier_specs[m].rates))]
    model.add_component(
        "samba_tier_kwh",
        pyo.Var(tier_index, within=pyo.NonNegativeReals),
    )
    tier_var: Any = model.component("samba_tier_kwh")

    # ---------------------------------------------------------------
    # 4. Tier upper-bound constraints  x[m,i] <= width_i
    # ---------------------------------------------------------------
    def _tier_ub(_m: Any, m: int, i: int) -> Any:
        spec = tier_specs[m]
        lower = spec.boundaries[i - 1] if i > 0 else 0.0
        upper = spec.boundaries[i]
        width = upper - lower
        if upper == float("inf") or width == float("inf"):
            return pyo.Constraint.Skip
        return tier_var[m, i] <= width

    model.add_component(
        "samba_tier_ub",
        pyo.Constraint(tier_index, rule=_tier_ub),
    )

    # ---------------------------------------------------------------
    # 5. Tier partition constraints  sum_i x[m,i] == M_m
    # ---------------------------------------------------------------
    def _tier_sum(_m: Any, m: int) -> Any:
        n_tiers = len(tier_specs[m].rates)
        return pyo.quicksum(tier_var[m, i] for i in range(n_tiers)) == mc_var[m]

    model.add_component(
        "samba_tier_sum",
        pyo.Constraint(range(12), rule=_tier_sum),
    )

    # ---------------------------------------------------------------
    # 6. Augment Pyomo objective with tiered grid cost
    # ---------------------------------------------------------------
    tiered_cost_expr = pyo.quicksum(
        tier_specs[m].rates[i] * tier_var[m, i]
        for m in range(12)
        for i in range(len(tier_specs[m].rates))
    )

    # Find the active Objective and augment it
    active_obj: Any = None
    for _name, comp in model.component_map(pyo.Objective).items():
        if comp.active:
            active_obj = comp
            break

    if active_obj is None:
        raise RuntimeError(
            "inject_tiered_cost: could not find an active Pyomo Objective in solph.Model"
        )

    active_obj.set_value(active_obj.expr + tiered_cost_expr)

    n_tier_vars = len(tier_index)
    log.info(
        "Injected endogenous PWL tiered tariff: 12 monthly consumption vars + "
        "%d tier decomposition vars",
        n_tier_vars,
    )
