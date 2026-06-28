# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Monthly flat electricity rate calculator.

Applies a different flat rate for each calendar month.

Builds the 8760-hour buy-rate array for this tariff structure.
"""

from __future__ import annotations

import numpy as np

_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def calc_monthly_rate(monthly_rates: list[float]) -> np.ndarray:
    """Build an 8 760-element rate array from 12 monthly flat rates.

    Parameters
    ----------
    monthly_rates:
        Exactly 12 electricity prices [$/kWh], one per calendar month
        (January ... December).

    Returns
    -------
    np.ndarray, shape (8760,)
        Hourly electricity price [$/kWh].

    Raises
    ------
    ValueError
        If *monthly_rates* does not contain exactly 12 values.
    """
    if len(monthly_rates) != 12:
        raise ValueError(f"monthly_rates must have exactly 12 elements; got {len(monthly_rates)}.")
    cbuy = np.zeros(8760, dtype=np.float64)
    h = 0
    for rate, days in zip(monthly_rates, _DAYS_IN_MONTH, strict=True):
        hours = 24 * days
        cbuy[h : h + hours] = rate
        h += hours
    return cbuy
