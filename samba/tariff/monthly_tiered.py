# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Monthly-tiered electricity rate calculator.

Each calendar month has its own tier schedule.  The applicable tier is
determined by the cumulative monthly load.

Builds the 8760-hour buy-rate array for this tariff structure.
"""

from __future__ import annotations

import numpy as np

from samba.scenario.models import TierLevel

_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _apply_tiers(monthly_kwh: float, tiers: list[TierLevel]) -> float:
    for tier in tiers:
        if tier.limit_kwh is None or monthly_kwh < tier.limit_kwh:
            return tier.rate_per_kwh
    return tiers[-1].rate_per_kwh


def calc_monthly_tiered_rate(
    monthly_tiers: list[list[TierLevel]],
    load_kw: np.ndarray,
) -> np.ndarray:
    """Build an 8 760-element rate array from per-month tiered pricing.

    Parameters
    ----------
    monthly_tiers:
        12-element list; each element is a list of
        :class:'~samba.scenario.models.TierLevel' for that month
        (January ... December).
    load_kw:
        Hourly load [kW], shape (8760,).

    Returns
    -------
    np.ndarray, shape (8760,)
        Marginal electricity price [$/kWh] for each hour.

    Raises
    ------
    ValueError
        If *monthly_tiers* does not contain exactly 12 month schedules.
    """
    if len(monthly_tiers) != 12:
        raise ValueError(f"monthly_tiers must have exactly 12 schedules; got {len(monthly_tiers)}.")
    cbuy = np.zeros(8760, dtype=np.float64)
    h = 0
    for tiers, days in zip(monthly_tiers, _DAYS_IN_MONTH, strict=True):
        monthly_kwh = 0.0
        for _ in range(24 * days):
            monthly_kwh += load_kw[h]
            cbuy[h] = _apply_tiers(monthly_kwh, tiers)
            h += 1
    return cbuy
