# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Core discount-rate helpers for NPC computation.

All monetary outputs are in the same currency as the input capex/opex values
(typically USD per the scenario ''currency'' field).

Notes
-----
These helpers form the numeric backbone of the SAMBA economics engine.  The
formulas follow standard techno-economic conventions (e.g. HOMER Pro):

* Costs are discounted using the **real** discount rate derived from the
  nominal rate and the inflation rate.
* The CRF function is shared with the compiler module
  (:mod:'samba.compiler.annualize').  This module provides the *inverse*
  helpers (present-worth factors) needed for post-solve KPI computation.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "real_discount_rate",
    "present_worth_factor",
    "single_payment_pv",
    "escalated_present_worth_factor",
]


def real_discount_rate(nominal: float, inflation: float) -> float:
    """Convert a nominal discount rate to a real (inflation-adjusted) rate.

    .. math::

       r_{real} = \\frac{r_{nom} - r_{inf}}{1 + r_{inf}}

    Parameters
    ----------
    nominal:
        Nominal annual discount rate (e.g. ''0.08'' = 8 %).
    inflation:
        Annual inflation rate (e.g. ''0.025'' = 2.5 %).

    Returns
    -------
    float
        Real discount rate as a decimal fraction.

    Examples
    --------
    >>> round(real_discount_rate(0.08, 0.025), 6)
    0.053659
    """
    return (nominal - inflation) / (1.0 + inflation)


def present_worth_factor(r: float, n: int) -> float:
    """Present worth factor (PWF) = sum of discount factors for years 1 .. n.

    .. math::

       PWF = \\frac{1 - (1+r)^{-n}}{r}

    This is the factor that converts a *uniform annual series* into its
    equivalent present-value lump sum.

    Parameters
    ----------
    r:
        Real annual discount rate (decimal fraction).
    n:
        Number of years (positive integer).

    Returns
    -------
    float
        Present worth factor (dimensionless multiplier applied to annual cost).

    Notes
    -----
    When ''r == 0'' the formula is indeterminate; the correct limit is ''n''.

    Examples
    --------
    >>> round(present_worth_factor(0.08, 25), 4)
    10.6748
    >>> present_worth_factor(0.0, 10)
    10.0
    """
    if n <= 0:
        return 0.0
    if r == 0.0:
        return float(n)
    return (1.0 - (1.0 + r) ** (-n)) / r


def single_payment_pv(r: float, t: int) -> float:
    """Present-value factor for a single payment at year *t*.

    .. math::

       PV = \\frac{1}{(1+r)^t}

    Parameters
    ----------
    r:
        Real annual discount rate (decimal fraction).
    t:
        Year of payment (positive integer).

    Returns
    -------
    float
        Discount factor <= 1.0.
    """
    if t <= 0:
        return 1.0
    return 1.0 / (1.0 + r) ** t


def escalated_present_worth_factor(r_real: float, escalation_rate: float, n: int) -> float:
    """Present-worth factor for a uniform series whose annual cost escalates.

    Each year *t* the cost is multiplied by ''(1 + escalation_rate)^t'' relative
    to year-1.  The series is then discounted at *r_real*.

    When *escalation_rate* is 0 this reduces to :func:'present_worth_factor'.

    Parameters
    ----------
    r_real:
        Real annual discount rate (decimal fraction).
    escalation_rate:
        Annual price escalation rate (decimal fraction; e.g. 0.02 = 2 %/yr).
    n:
        Project lifetime in years.

    Returns
    -------
    float
        Sum of discounted escalating annual factors.
    """
    if n <= 0:
        return 0.0
    if escalation_rate == 0.0:
        return present_worth_factor(r_real, n)
    t = np.arange(1, n + 1, dtype=np.float64)
    return float(np.sum((1.0 + escalation_rate) ** t / (1.0 + r_real) ** t))
