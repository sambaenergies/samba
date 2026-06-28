# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Ultra-low TOU (UL-TOU) electricity rate calculator.

Identical to the standard TOU calculator except that every hour of the year
**must** be covered by at least one :class:'~samba.scenario.models.TouPeriod'.
A ''ValueError'' is raised if any hour is left unassigned.

Builds the 8760-hour buy-rate array for this tariff structure.
"""

from __future__ import annotations

import numpy as np

from samba.scenario.models import TouPeriod
from samba.tariff.tou import _build_hour_metadata, calc_tou_rate


def calc_ultra_low_tou_rate(
    tou_periods: list[TouPeriod],
    year: int = 2025,
) -> np.ndarray:
    """Build an 8 760-element rate array from UL-TOU periods.

    Every hour of the year must be assigned a rate.  This is the UL-TOU
    ("Ultra-Low TOU") constraint: no hour is permitted to fall through the
    schedule uncovered.

    Parameters
    ----------
    tou_periods:
        Complete set of :class:'~samba.scenario.models.TouPeriod' objects that
        together cover all 8 760 hours.
    year:
        Calendar year used to determine weekday/weekend for each date.

    Returns
    -------
    np.ndarray, shape (8760,)
        Hourly electricity price [$/kWh].

    Raises
    ------
    ValueError
        If any hour is not covered by a period (rate would remain 0.0 from
        initialisation but no period assigned it).
    """
    # Track which hours were explicitly assigned using a sentinel of NaN.
    # We build the array with NaN and use the TOU logic to fill it.
    n = 8760
    cbuy = np.full(n, np.nan, dtype=np.float64)

    month_arr, hour_arr, weekday_arr = _build_hour_metadata(year)

    for period in tou_periods:
        month_set = set(period.months)
        hour_set = set(period.hours)

        in_month = np.isin(month_arr, list(month_set))
        in_hour = np.isin(hour_arr, list(hour_set))

        if period.weekday and period.weekend:
            day_mask = np.ones(n, dtype=bool)
        elif period.weekday:
            day_mask = weekday_arr == 1
        elif period.weekend:
            day_mask = weekday_arr == 0
        else:
            continue

        mask = in_month & in_hour & day_mask
        cbuy[mask] = period.rate_per_kwh

    unassigned = np.sum(np.isnan(cbuy))
    if unassigned > 0:
        raise ValueError(
            f"UL-TOU schedule leaves {unassigned} hour(s) unassigned. "
            "Every hour of the year must be covered by at least one TouPeriod."
        )

    return cbuy


# Keep a convenience alias so the resolver can call either calculator uniformly.
calc_tou_rate = calc_tou_rate  # re-export for symmetry
