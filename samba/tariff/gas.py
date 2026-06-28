# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Gas rate array builder for Phase 23.

Produces an 8 760-element ``$/kWh_th`` rate array from a
:class:`~samba.scenario.models.GasTariff` configuration.

Supported rate types
--------------------
- ``"flat"``     -- constant rate all year.
- ``"seasonal"`` -- different flat rate per season (calendar-month based).
- ``"tiered"``   -- increasing-block tariff; **pre-computed** using first-tier
  marginal rate (conservative v3 approximation -- endogenous tiering is v4+).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from samba.thermal.gas_constants import convert_gas_rate

if TYPE_CHECKING:
    from samba.scenario.models._components import GasTariff

__all__ = ["build_gas_rate_array"]

_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def build_gas_rate_array(tariff: GasTariff) -> np.ndarray:
    """Build an 8 760-element gas rate array [$/kWh_th].

    Parameters
    ----------
    tariff:
        Validated :class:`~samba.scenario.models.GasTariff` configuration.

    Returns
    -------
    np.ndarray, shape (8760,)
        Hourly natural gas price in $/kWh_th for the LP objective.

    Notes
    -----
    **Tiered gas rates** are pre-computed using the first-tier marginal rate as
    a conservative approximation.  The optimizer will see this constant rate
    and dispatch gas accordingly.  Endogenous (per-LP-iteration) tiered gas
    modeling is deferred to v4.
    """
    unit = tariff.unit

    if tariff.rate_type == "flat":
        rate_kwh = convert_gas_rate(float(tariff.flat_rate), unit)  # type: ignore[arg-type]
        return np.full(8760, rate_kwh, dtype=np.float64)

    if tariff.rate_type == "seasonal":
        month_rate: dict[int, float] = {}
        for s in tariff.seasonal_schedule:  # type: ignore[union-attr]
            r = convert_gas_rate(s.rate, unit)
            for m in s.months:
                month_rate[m] = r
        arr = np.zeros(8760, dtype=np.float64)
        h = 0
        for month_idx, days in enumerate(_DAYS_IN_MONTH, start=1):
            arr[h : h + days * 24] = month_rate.get(month_idx, 0.0)
            h += days * 24
        return arr

    # tiered -- use first-tier marginal rate (pre-compute approximation)
    tiered_rates = tariff.tiered_rates
    if not tiered_rates:
        raise ValueError("gas.tiered_rates must be provided for gas.rate_type='tiered'")

    first_rate_kwh = convert_gas_rate(float(tiered_rates[0]), unit)
    return np.full(8760, first_rate_kwh, dtype=np.float64)
