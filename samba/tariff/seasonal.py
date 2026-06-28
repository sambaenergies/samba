# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Seasonal flat electricity rate calculator.

Each :class:'~samba.scenario.models.SeasonalRate' specifies a set of calendar
months and a flat rate that applies during those months.  Months not covered by
any season receive a rate of 0.0.

Builds the 8760-hour buy-rate array for this tariff structure.
"""

from __future__ import annotations

import numpy as np

from samba.scenario.models import SeasonalRate

_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def calc_seasonal_rate(seasonal_schedule: list[SeasonalRate]) -> np.ndarray:
    """Build an 8 760-element rate array from seasonal flat rates.

    Parameters
    ----------
    seasonal_schedule:
        List of :class:'~samba.scenario.models.SeasonalRate' objects.  If
        multiple entries cover the same month the *last* one wins.

    Returns
    -------
    np.ndarray, shape (8760,)
        Hourly electricity price [$/kWh].  Uncovered months receive 0.0.
    """
    # Build a month -> rate lookup (1-indexed; month 0 unused).
    month_rate: dict[int, float] = {}
    for season in seasonal_schedule:
        for m in season.months:
            month_rate[m] = season.rate_per_kwh

    cbuy = np.zeros(8760, dtype=np.float64)
    h = 0
    for month_idx, days in enumerate(_DAYS_IN_MONTH, start=1):
        rate = month_rate.get(month_idx, 0.0)
        hours = 24 * days
        cbuy[h : h + hours] = rate
        h += hours
    return cbuy
