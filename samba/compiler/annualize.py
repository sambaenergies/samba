# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Annualized capital cost helpers.

These helpers convert a one-time capital expenditure (CAPEX) into an annual
equivalent cost using the Capital Recovery Factor (CRF) formula -- the standard
economic formulation used by HOMER Pro and most techno-economic microgrid tools.

The annualized cost is then passed to oemof-solph as ''ep_costs'' on
''solph.Investment'' objects so that the LP/MILP objective reflects the true
lifetime-discounted cost of each investment decision.
"""

from __future__ import annotations

__all__ = ["crf", "ep_costs", "real_discount_rate"]


def real_discount_rate(nominal: float, inflation: float) -> float:
    """Convert a nominal discount rate to a real (inflation-adjusted) rate.

    Uses the exact Fisher equation (standard economics):

    .. math::

       r_{real} = \\frac{r_{nom} - r_{inf}}{1 + r_{inf}}

    Parameters
    ----------
    nominal:
        Nominal annual discount rate as a decimal fraction (e.g. ''0.045'').
    inflation:
        Annual inflation rate as a decimal fraction (e.g. ''0.02'').

    Returns
    -------
    float
        Real discount rate.

    Examples
    --------
    >>> round(real_discount_rate(0.045, 0.02), 6)
    0.02451
    """
    return (nominal - inflation) / (1.0 + inflation)


def crf(rate: float, lifetime_years: int) -> float:
    """Capital Recovery Factor.

    Converts a present-value cost into an equal annual payment series over
    *lifetime_years* at discount *rate*.

    .. math::

       CRF = \\frac{r(1+r)^n}{(1+r)^n - 1}

    Parameters
    ----------
    rate:
        Annual discount rate as a decimal fraction (e.g. ''0.08'' = 8 %).
    lifetime_years:
        Component economic lifetime in years (positive integer).

    Returns
    -------
    float
        CRF in units of year-1.

    Notes
    -----
    When ''rate == 0'' the formula is indeterminate; the correct limit is
    ''1 / lifetime_years'' (uniform straight-line recovery).

    Examples
    --------
    >>> round(crf(0.08, 25), 4)
    0.0937
    >>> crf(0.0, 10)
    0.1
    """
    if rate == 0.0:
        return 1.0 / lifetime_years
    r = rate
    n = float(lifetime_years)
    factor = float((1.0 + r) ** n)
    return (r * factor) / (factor - 1.0)


def ep_costs(capex: float, rate: float, lifetime_years: int) -> float:
    """Annualized capital cost suitable for use as ''ep_costs'' in oemof.

    Parameters
    ----------
    capex:
        Total capital expenditure in the project currency (e.g. USD).
    rate:
        Annual discount rate as a decimal fraction.
    lifetime_years:
        Component economic lifetime in years.

    Returns
    -------
    float
        Annual equivalent cost = ''capex * CRF(rate, lifetime_years)''.

    Examples
    --------
    >>> round(ep_costs(10_000, 0.08, 25), 2)
    937.0
    """
    return capex * crf(rate, lifetime_years)
