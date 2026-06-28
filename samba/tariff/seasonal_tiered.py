# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Seasonal-tiered electricity rate calculator.

Combines seasonal differentiation with increasing-block (tiered) pricing.
Each :class:'~samba.scenario.models.SeasonalTiers' specifies a season (months)
and a tier schedule.  The applicable tier is determined by the cumulative
monthly load, as in the plain tiered calculator.

Builds the 8760-hour buy-rate array for this tariff structure.
"""

from __future__ import annotations

import numpy as np

from samba.scenario.models import SeasonalTiers, TierLevel

_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _apply_tiers(monthly_kwh: float, tiers: list[TierLevel]) -> float:
    """Return the marginal rate for the given cumulative monthly usage."""
    for tier in tiers:
        if tier.limit_kwh is None or monthly_kwh < tier.limit_kwh:
            return tier.rate_per_kwh
    return tiers[-1].rate_per_kwh


def calc_seasonal_tiered_rate(
    seasonal_tiers: list[SeasonalTiers],
    load_kw: np.ndarray,
) -> np.ndarray:
    """Build an 8 760-element rate array from seasonal tiered pricing.

    Parameters
    ----------
    seasonal_tiers:
        List of :class:'~samba.scenario.models.SeasonalTiers'.  If multiple
        entries cover the same month the *last* one wins.
    load_kw:
        Hourly load [kW], shape (8760,).  Used to compute cumulative monthly
        consumption and determine the applicable tier each hour.

    Returns
    -------
    np.ndarray, shape (8760,)
        Marginal electricity price [$/kWh] for each hour.
    """
    # Build month -> tiers lookup
    month_tiers: dict[int, list[TierLevel]] = {}
    for st in seasonal_tiers:
        for m in st.months:
            month_tiers[m] = st.tiers

    cbuy = np.zeros(8760, dtype=np.float64)
    h = 0
    for month_idx, days in enumerate(_DAYS_IN_MONTH, start=1):
        tiers = month_tiers.get(month_idx)
        monthly_kwh = 0.0
        for _ in range(24 * days):
            monthly_kwh += load_kw[h]
            cbuy[h] = _apply_tiers(monthly_kwh, tiers) if tiers else 0.0
            h += 1
    return cbuy
