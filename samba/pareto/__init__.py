# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""samba.pareto -- Weighted-sum Pareto front generation for cost-emissions trade-offs.

The :func:'~samba.pareto.sweep.run_pareto_sweep' function runs the SAMBA
optimisation N times with varying ''emissions_weight'' (carbon price, $/kg
CO2) values, collects the resulting ''(NPC, LEM)'' pairs, and returns the
non-dominated subset as a list of :class:'~samba.pareto.sweep.ParetoPoint'.

**Important:** This is a *weighted-sum approximation* of the Pareto front, not
a true multi-objective solve.  Non-convex regions of the true Pareto frontier
may be missed.  See the ''samba pareto'' CLI help for details.
"""

from __future__ import annotations

from samba.pareto.sweep import (
    ParetoPoint,
    default_alpha_range,
    run_pareto_sweep,
    run_pareto_sweep_epsilon,
)

__all__ = [
    "ParetoPoint",
    "default_alpha_range",
    "run_pareto_sweep",
    "run_pareto_sweep_epsilon",
]
