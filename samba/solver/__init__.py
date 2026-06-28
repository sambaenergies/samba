# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Solver integration sub-package.

Public API
----------
.. currentmodule:: samba.solver

:func:'solve'
    Run CBC (or another LP solver) on an ''oemof.solph.EnergySystem'' and
    return a ''solph.Results'' object.

:class:'SolverConfig'
    Configuration dataclass for solver name, time limit, MIP gap, verbosity.

:func:'extract_dispatch'
    Convert a ''solph.Results'' object to a structured :class:'DispatchResult'.

:func:'validate_energy_balance'
    Assert that the AC bus is balanced at every timestep within tolerance.

Exceptions
----------
:exc:'SolverError', :exc:'InfeasibleError', :exc:'SolverNotFoundError',
:exc:'SolverTimeLimitError', :exc:'EnergyBalanceError'
"""

from samba.solver.extract import (
    DispatchResult,
    EnergyBalanceError,
    extract_dispatch,
    validate_energy_balance,
)
from samba.solver.runner import (
    InfeasibleError,
    SolverConfig,
    SolverError,
    SolverNotFoundError,
    SolverTimeLimitError,
    solve,
)

__all__ = [
    "DispatchResult",
    "EnergyBalanceError",
    "InfeasibleError",
    "SolverConfig",
    "SolverError",
    "SolverNotFoundError",
    "SolverTimeLimitError",
    "extract_dispatch",
    "solve",
    "validate_energy_balance",
]
