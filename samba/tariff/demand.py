# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Demand-charge and NEM-reconciliation math (v4).

These functions operate on the *solved* 8760-h dispatch so the economics layer
and (for demand charges) the LP constraint injector share a single source of
truth for the monthly-peak and monthly-reconciliation logic.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "HOURS_PER_YEAR",
    "hour_month_index",
    "monthly_peak_import",
    "annual_demand_charge",
    "nem_annual_grid_cost",
]

HOURS_PER_YEAR = 8760
_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)  # non-leap


def hour_month_index() -> np.ndarray:
    """Return an ``(8760,)`` int array mapping each hour-of-year to its month (0-11)."""
    months = np.empty(HOURS_PER_YEAR, dtype=np.int64)
    h = 0
    for month, days in enumerate(_DAYS_IN_MONTH):
        n = days * 24
        months[h : h + n] = month
        h += n
    return months


def _hour_of_day() -> np.ndarray:
    """Return an ``(8760,)`` int array of the hour-of-day (0-23) for each hour-of-year."""
    return np.arange(HOURS_PER_YEAR, dtype=np.int64) % 24


def monthly_peak_import(grid_buy: np.ndarray, hours: list[int] | None = None) -> np.ndarray:
    """Peak grid-import power [kW] in each calendar month.

    Parameters
    ----------
    grid_buy:
        8760-element hourly grid import [kW].
    hours:
        If given, only hours-of-day in this set count toward the peak (e.g. an
        on-peak demand window). ``None`` = every hour.

    Returns
    -------
    np.ndarray
        ``(12,)`` array of the monthly peak import [kW]. Months with no eligible
        non-zero hour are 0.
    """
    gb = np.asarray(grid_buy, dtype=np.float64)
    months = hour_month_index()
    if hours is not None:
        mask = np.isin(_hour_of_day(), list(hours))
        gb = np.where(mask, gb, 0.0)
    peaks = np.zeros(12, dtype=np.float64)
    for m in range(12):
        sel = gb[months == m]
        if sel.size:
            peaks[m] = float(sel.max())
    return peaks


def annual_demand_charge(
    grid_buy: np.ndarray, rate_per_kw_month: float, hours: list[int] | None = None
) -> float:
    """Year-1 demand charge [$] = Σ_months (rate $/kW-month × monthly peak kW)."""
    if rate_per_kw_month <= 0.0:
        return 0.0
    return float(rate_per_kw_month * monthly_peak_import(grid_buy, hours).sum())


def nem_annual_grid_cost(
    grid_buy: np.ndarray,
    grid_sell: np.ndarray,
    cbuy: np.ndarray,
    csell: np.ndarray,
    *,
    carryover: bool = True,
    annual_excess_credit_fraction: float = 0.0,
) -> float:
    """Year-1 net grid energy cost [$] under monthly NEM reconciliation.

    Each month's net bill (``bought$ − sold$``) is reduced by any carried credit
    and floored at $0; surplus becomes credit (carried forward if ``carryover``).
    Leftover year-end credit is paid back scaled by ``annual_excess_credit_fraction``.

    Returns the net annual energy cost (positive = customer pays). Excludes the
    fixed service charge, which is added separately.
    """
    gb = np.asarray(grid_buy, dtype=np.float64)
    gs = np.asarray(grid_sell, dtype=np.float64)
    cb = np.asarray(cbuy, dtype=np.float64)
    cs = np.asarray(csell, dtype=np.float64)
    months = hour_month_index()

    total_bill = 0.0
    credit = 0.0  # carried export credit [$]
    for m in range(12):
        sel = months == m
        bought = float(np.dot(gb[sel], cb[sel]))
        sold = float(np.dot(gs[sel], cs[sel]))
        net = bought - sold - credit
        if net >= 0.0:
            total_bill += net
            credit = 0.0
        else:
            # surplus this month; bill floored at 0, surplus becomes credit
            credit = -net if carryover else 0.0
    # Settle leftover credit at year end (paid back to customer => reduces cost).
    total_bill -= annual_excess_credit_fraction * credit
    return total_bill
