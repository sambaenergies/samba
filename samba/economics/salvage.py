# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Salvage value computation at end of project lifetime.

If a component's remaining useful life at the end of the project is positive
(i.e. the project ends before the component's next replacement cycle) the
component retains a fraction of its capital value--this is the *salvage value*.
Salvage reduces NPC.
"""

from __future__ import annotations

__all__ = [
    "salvage_fraction",
    "salvage_npv",
]

from samba.economics.npc import single_payment_pv


def salvage_fraction(project_yrs: int, component_lifetime: int) -> float:
    """Remaining life fraction at end of project.

    .. math::

       f = \\begin{cases}
           (L - (N \\bmod L)) / L & \\text{if } N \\bmod L \\neq 0 \\\\
           0 & \\text{otherwise}
       \\end{cases}

    where :math:'L' = ''component_lifetime'' and :math:'N' = ''project_yrs''.

    When the project ends on a replacement boundary (''N % L == 0'') the
    component has zero remaining life and salvage value is 0.

    Parameters
    ----------
    project_yrs:
        Total project lifetime in years.
    component_lifetime:
        Component service lifetime in years; must be > 0.

    Returns
    -------
    float
        Salvage fraction in [0, 1).

    Examples
    --------
    >>> salvage_fraction(25, 10)
    0.5
    >>> salvage_fraction(20, 10)
    0.0
    >>> salvage_fraction(25, 25)
    0.0
    """
    if component_lifetime <= 0:
        raise ValueError(f"component_lifetime must be > 0, got {component_lifetime}")
    years_used = project_yrs % component_lifetime
    if years_used == 0:
        return 0.0
    return (component_lifetime - years_used) / component_lifetime


def salvage_npv(
    capex: float,
    project_yrs: int,
    component_lifetime: int,
    r_real: float,
) -> float:
    """Present value of the salvage (residual) capital at end of project.

    The salvage is paid *to* the project owner at year ''project_yrs'', so it
    is a **negative** cost term that reduces NPC.

    .. math::

       NPV_{salv} = capex \\cdot f_{salv} \\cdot \\frac{1}{(1+r)^N}

    Parameters
    ----------
    capex:
        Original capital cost in real (today's) dollars.
    project_yrs:
        Total project lifetime in years.
    component_lifetime:
        Component service lifetime in years.
    r_real:
        Real annual discount rate (decimal fraction).

    Returns
    -------
    float
        Present value of salvage (non-negative). Subtract from NPC.

    Examples
    --------
    >>> round(salvage_npv(10_000, 25, 10, 0.06), 2)
    2741.27
    """
    frac = salvage_fraction(project_yrs, component_lifetime)
    return capex * frac * single_payment_pv(r_real, project_yrs)
