# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Tiered (increasing-block) electricity rate calculator.

Each tier defines an upper consumption limit and a marginal rate [$/kWh].  The
rate applied to each hour is the marginal rate of the tier that the *current
cumulative monthly usage* falls within.

Builds the 8760-hour buy-rate array for this tariff structure.
"""

from __future__ import annotations

import numpy as np

from samba.scenario.models import TierLevel

_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def calc_tiered_rate(
    tiers: list[TierLevel],
    load_kw: np.ndarray,
) -> np.ndarray:
    """Build an 8 760-element rate array using an increasing-block tariff.

    Parameters
    ----------
    tiers:
        At least one :class:'~samba.scenario.models.TierLevel'.  The final
        tier must have ''limit_kwh=None'' (unlimited top tier).
    load_kw:
        Hourly load [kW], shape (8760,).  Used to track monthly cumulative
        consumption and determine the applicable tier each hour.

    Returns
    -------
    np.ndarray, shape (8760,)
        Marginal electricity price [$/kWh] for each hour.

    Raises
    ------
    ValueError
        If *tiers* is empty or the top tier has a finite ''limit_kwh''.
    """
    if not tiers:
        raise ValueError("tiers must contain at least one TierLevel.")
    if tiers[-1].limit_kwh is not None:
        raise ValueError("The last TierLevel must have limit_kwh=None (unbounded top tier).")

    # Precompute tier limits and rates as plain arrays for fast lookup.
    limits = [t.limit_kwh if t.limit_kwh is not None else np.inf for t in tiers]
    rates = [t.rate_per_kwh for t in tiers]

    cbuy = np.zeros(8760, dtype=np.float64)
    h = 0
    for days in _DAYS_IN_MONTH:
        monthly_kwh = 0.0
        for _ in range(24 * days):
            monthly_kwh += load_kw[h]
            # Find the applicable tier (first limit larger than running total)
            rate = rates[-1]
            for limit, r in zip(limits, rates, strict=True):
                if monthly_kwh < limit:
                    rate = r
                    break
            cbuy[h] = rate
            h += 1
    return cbuy
