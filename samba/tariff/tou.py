# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Time-of-Use (TOU) electricity rate calculator.

Each :class:'~samba.scenario.models.TouPeriod' specifies the months, day types
(weekday / weekend), hours, and rate that apply.  Periods are evaluated in
order; later entries override earlier ones for overlapping hours.

Unassigned hours receive a rate of 0.0.  See ''ultra_low_tou.py'' for the
variant that raises ''ValueError'' when any hour is unassigned.
"""

from __future__ import annotations

import datetime

import numpy as np

from samba.scenario.models import TouPeriod

# Standard non-leap-year month lengths (SAMBA v1 operates on 8 760 h/yr).
_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _build_hour_metadata(year: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return month[8760], hour_of_day[8760], is_weekday[8760] for *year*.

    ''is_weekday[i] == 1'' if hour *i* falls on Mon-Fri.
    """
    month_arr = np.empty(8760, dtype=np.int32)
    hour_arr = np.empty(8760, dtype=np.int32)
    weekday_arr = np.empty(8760, dtype=np.int32)  # 1 = weekday, 0 = weekend

    idx = 0
    for m, days in enumerate(_DAYS_IN_MONTH, start=1):
        for d in range(1, days + 1):
            dt = datetime.date(year, m, d)
            is_wd = int(dt.weekday() < 5)  # Mon=0 ... Fri=4 are weekdays
            for h in range(24):
                month_arr[idx] = m
                hour_arr[idx] = h
                weekday_arr[idx] = is_wd
                idx += 1
    return month_arr, hour_arr, weekday_arr


def calc_tou_rate(
    tou_periods: list[TouPeriod],
    year: int = 2025,
) -> np.ndarray:
    """Build an 8 760-element rate array from a list of TOU periods.

    Parameters
    ----------
    tou_periods:
        Ordered list of :class:'~samba.scenario.models.TouPeriod' objects.
        Later entries in the list override earlier ones for the same hour.
    year:
        Calendar year used to determine weekday/weekend for each date.

    Returns
    -------
    np.ndarray, shape (8760,)
        Hourly electricity price [$/kWh].  Unassigned hours are 0.0.
    """
    cbuy = np.zeros(8760, dtype=np.float64)
    month_arr, hour_arr, weekday_arr = _build_hour_metadata(year)

    for period in tou_periods:
        month_set = set(period.months)
        hour_set = set(period.hours)

        in_month = np.isin(month_arr, list(month_set))
        in_hour = np.isin(hour_arr, list(hour_set))

        # Day-type mask
        if period.weekday and period.weekend:
            day_mask = np.ones(8760, dtype=bool)
        elif period.weekday:
            day_mask = weekday_arr == 1
        elif period.weekend:
            day_mask = weekday_arr == 0
        else:
            # Neither -> period never applies (degenerate case)
            continue

        mask = in_month & in_hour & day_mask
        cbuy[mask] = period.rate_per_kwh

    return cbuy
