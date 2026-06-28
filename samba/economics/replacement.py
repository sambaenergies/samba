# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Component replacement scheduling and NPV computation.

Battery, inverter, and other components with lifetimes shorter than the
project lifetime must be replaced at regular intervals.  This module computes
which years replacements occur and the net-present cost of those replacements.
"""

from __future__ import annotations

__all__ = [
    "replacement_years",
    "replacement_npv",
    "replacement_count",
]

from samba.economics.npc import single_payment_pv


def replacement_years(project_yrs: int, component_lifetime: int) -> list[int]:
    """Return the years at which a component must be replaced.

    Replacements occur at :math:'t = lifetime, 2 \\times lifetime, \\ldots'
    while :math:'t < project\\_yrs'.  A replacement at exactly the final year
    of the project is **included** only if ''project_yrs > component_lifetime''.

    In practice, if ''component_lifetime == project_yrs'' there are **no**
    intermediate replacements--the component installed at year 0 covers the
    whole project period.

    Parameters
    ----------
    project_yrs:
        Total project lifetime in years.
    component_lifetime:
        Component service lifetime in years; must be > 0.

    Returns
    -------
    list[int]
        Sorted list of years at which the component is replaced (may be empty).

    Examples
    --------
    >>> replacement_years(25, 10)
    [10, 20]
    >>> replacement_years(25, 25)
    []
    >>> replacement_years(20, 10)
    [10]
    """
    if component_lifetime <= 0:
        raise ValueError(f"component_lifetime must be > 0, got {component_lifetime}")
    return list(range(component_lifetime, project_yrs, component_lifetime))


def replacement_count(project_yrs: int, component_lifetime: int) -> int:
    """Number of replacement events over the project lifetime.

    Convenience wrapper around :func:'replacement_years'.

    Examples
    --------
    >>> replacement_count(25, 10)
    2
    >>> replacement_count(25, 25)
    0
    """
    return len(replacement_years(project_yrs, component_lifetime))


def replacement_npv(
    capex: float,
    project_yrs: int,
    component_lifetime: int,
    r_real: float,
) -> float:
    """Net present cost of all replacement events for a component.

    Each replacement costs the same nominal ''capex'' (expressed in today's
    dollars, i.e. real terms), discounted back to year 0 at the real rate.

    .. math::

       NPV_{rep} = \\sum_{t \\in rep\\_years} \\frac{capex}{(1+r)^t}

    Parameters
    ----------
    capex:
        Replacement capital cost in real (today's) dollars.
    project_yrs:
        Total project lifetime in years.
    component_lifetime:
        Component service lifetime in years.
    r_real:
        Real annual discount rate (decimal fraction).

    Returns
    -------
    float
        Present value of all replacement costs (non-negative).

    Examples
    --------
    >>> round(replacement_npv(10_000, 25, 10, 0.06), 2)
    8739.37
    """
    years = replacement_years(project_yrs, component_lifetime)
    return sum(capex * single_payment_pv(r_real, t) for t in years)
