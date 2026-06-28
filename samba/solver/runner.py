# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Solver runner for oemof-solph energy system models.

This module wraps the oemof-solph / Pyomo solve call with:

* A typed :class:'SolverConfig' configuration dataclass.
* A clean exception hierarchy for all failure modes.
* Deterministic termination-condition inspection (uses ''allow_nonoptimal=True''
  so we control the error type, rather than parsing exception message strings).
* Constraint injection (calls :func:'inject_hard_constraints' between model
  construction and the solve call -- Pyomo constraints must be added before
  ''model.solve()'').
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import oemof.solph as solph

from samba.compiler.constraints import inject_hard_constraints

if TYPE_CHECKING:
    from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = [
    "SolverConfig",
    "SolverError",
    "InfeasibleError",
    "SolverNotFoundError",
    "SolverTimeLimitError",
    "solve",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class SolverConfig:
    """Configuration for the LP/MILP solver.

    Attributes
    ----------
    solver_name:
        Solver name passed to Pyomo's ''SolverFactory''.  Defaults to
        ''"appsi_highs"'' (HiGHS via Pyomo's APPSI interface, free and
        pip-installable via ''highspy'').  Also accepts ''"cbc"'' or ''"glpk"''.
    solver_io:
        Pyomo solver interface format.  ''""'' (empty) means auto-detect:
        HiGHS (''appsi_highs'') uses ''None'' (APPSI -- no LP file, calls
        ''highspy'' Python bindings directly); CBC/GLPK use ''"lp"''.
        Set explicitly to override.
    time_limit_s:
        Wall-clock time limit in seconds.  The solver is asked to stop after
        this many seconds; partial solutions are discarded.
    mip_gap:
        Relative MIP optimality gap.  HiGHS: ''mip_rel_gap''; CBC: ''ratioGap''.
        Has no effect for pure LP problems.
    output_verbose:
        If ''True'', solver output is streamed to stdout (''tee=True'').
    kibam_validate:
        If ''True'' (default), the KiBaM two-tank feasibility check runs after
        the solve when ''battery.chemistry == "kibam"''.  Set ''False'' to skip.
    strict_kibam:
        If ''True'', KiBaM dispatch violations detected by the post-solve check
        raise :class:'~samba.compiler.constraints.ConstraintViolationError'
        instead of only logging a warning.  Defaults to ''False'' because the
        LP relaxation produces a small, bounded number of violations near low
        SOC (see ''docs/known-limitations.md''); enable it to fail hard.
    """

    solver_name: str = "appsi_highs"
    solver_io: str = ""  # "" = auto-detect: None for appsi_highs, "lp" for CBC/GLPK
    time_limit_s: int = 600
    mip_gap: float = 0.01
    output_verbose: bool = False
    # MILP-specific overrides (used when NonConvex flows are detected)
    milp_time_limit_s: int = 1200  # double the LP default; UC solves take longer
    milp_mip_gap: float = 0.02  # slightly looser gap for MILP
    # KiBaM post-solve validation (only runs when battery.chemistry == "kibam")
    kibam_validate: bool = True  # set False to skip two-tank feasibility check
    strict_kibam: bool = False  # if True, KiBaM dispatch violations raise instead of warn


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SolverError(RuntimeError):
    """Base class for all solver-related failures."""


class InfeasibleError(SolverError):
    """Raised when the problem is infeasible or unbounded."""


class SolverNotFoundError(SolverError):
    """Raised when the requested solver executable is not installed."""


class SolverTimeLimitError(SolverError):
    """Raised when the solver hit the time limit without finding an optimal solution."""


# ---------------------------------------------------------------------------
# Solve function
# ---------------------------------------------------------------------------


def solve(
    energy_system: Any,  # solph.EnergySystem
    scenario: Scenario,
    config: SolverConfig | None = None,
) -> Any:  # solph.Results
    """Solve *energy_system* and return a :class:'solph.Results' object.

    The function:

    1. Builds a ''solph.Model'' from the energy system.
    2. Injects hard Pyomo constraints (budget, min-RE fraction) via
       :func:'~samba.compiler.constraints.inject_hard_constraints'.
    3. Calls ''model.solve(allow_nonoptimal=True)'' so we can inspect the
       termination condition ourselves.
    4. Raises a typed exception for infeasible, not-found, or time-limit
       outcomes.
    5. Returns ''solph.Results(model)''.

    Parameters
    ----------
    energy_system:
        A fully compiled ''solph.EnergySystem'' (from Phase 4).
    scenario:
        The validated scenario; passed to :func:'inject_hard_constraints' so
        constraint parameters are available.
    config:
        Solver configuration.  Defaults to ''SolverConfig()'' (CBC, 600 s).

    Returns
    -------
    solph.Results
        The new-style 0.6.3 Results object.  Access flows via
        ''results.get("flow")'', investments via ''results.get("invest")'',
        and storage content via ''results.get("storage_content")''.

    Raises
    ------
    SolverNotFoundError
        If the solver executable is not found on ''PATH''.
    InfeasibleError
        If the problem is infeasible or unbounded.
    SolverTimeLimitError
        If the solver hit the time limit without reaching optimality.
    SolverError
        For any other non-optimal termination.
    """
    if config is None:
        config = SolverConfig()

    # ------------------------------------------------------------------
    # 1. Build Pyomo model
    # ------------------------------------------------------------------
    log.info("Building solph.Model ...")
    t0 = time.perf_counter()
    model: Any = solph.Model(energy_system)

    # ------------------------------------------------------------------
    # 2. Inject hard constraints (must happen before model.solve())
    # ------------------------------------------------------------------
    inject_hard_constraints(model, scenario, energy_system)

    # ------------------------------------------------------------------
    # 2b. Inject endogenous PWL tiered tariff (Phase 17)
    # ------------------------------------------------------------------
    _buy = scenario.tariff.buy
    if _buy.endogenous_tiering and _buy.type in ("tiered", "seasonal_tiered", "monthly_tiered"):
        from samba.tariff.endogenous import (  # lazy import to avoid circular deps
            build_tier_specs,
            inject_tiered_cost,
            validate_tier_specs,
        )

        _specs = build_tier_specs(_buy)
        validate_tier_specs(_specs)
        inject_tiered_cost(model, energy_system, _specs)
        log.info("Endogenous PWL tiered tariff injected (%d months)", 12)

    # ------------------------------------------------------------------
    # 2c. Detect MILP mode (NonConvex flows introduce binary variables)
    # ------------------------------------------------------------------
    is_milp = hasattr(model, "NonConvexFlowBlock")
    if is_milp:
        effective_time_limit = config.milp_time_limit_s
        effective_mip_gap = config.milp_mip_gap
        log.info(
            "MILP mode detected (NonConvexFlowBlock present). MIP gap=%.3f, time limit=%ds",
            effective_mip_gap,
            effective_time_limit,
        )
    else:
        effective_time_limit = config.time_limit_s
        effective_mip_gap = config.mip_gap

    # ------------------------------------------------------------------
    # 3. Solve (allow_nonoptimal=True so we inspect the condition ourselves)
    # ------------------------------------------------------------------
    log.info(
        "Solving with solver=%r  time_limit=%ds  mip_gap=%.3f  milp=%s ...",
        config.solver_name,
        effective_time_limit,
        effective_mip_gap,
        is_milp,
    )

    # Build solver-specific keyword arguments.
    #
    # HiGHS (via Pyomo APPSI + highspy Python API)
    #   appsi_highs doesn't accept solver_io, so we BYPASS oemof's model.solve()
    #   and drive the solve directly, then patch model.solver_results so that
    #   the rest of our termination-condition logic can remain identical.
    #
    # CBC / GLPK (LP-file interface, via oemof's model.solve())
    #   solver_io="lp", options passed via cmdline_options dict
    #   CBC keys: sec (seconds), ratioGap (float)
    #   GLPK keys: tmlim (seconds), mipgap (float)
    solver_name_lower = config.solver_name.lower()
    _is_highs = solver_name_lower in ("highs", "highs_cmdline", "appsi_highs")
    _is_glpk = solver_name_lower == "glpk"

    try:
        if _is_highs:
            # APPSI path: oemof's model.solve() passes solver_io= to
            # SolverFactory, but appsi_highs rejects that kwarg.  We call the
            # solver directly and patch the model attributes that oemof would
            # normally set, so that solph.Results(model) still works.
            import pyomo.environ as pyo  # registers APPSI solver plugins

            opt = pyo.SolverFactory("appsi_highs")
            if effective_time_limit > 0:
                opt.options["time_limit"] = float(effective_time_limit)
            opt.options["mip_rel_gap"] = effective_mip_gap

            # APPSI compatibility: oemof-solph sets model.dual = None and
            # model.rc = None as plain Python __dict__ entries (not registered
            # Pyomo components).  Pyomo's APPSI LegacySolverInterface.solve()
            # checks BOTH model.dual.import_enabled() and
            # model.rc.import_enabled(), which crash when the value is None.
            # Removing both attributes via __dict__.pop makes hasattr() return
            # False, so APPSI skips dual/RC loading entirely.
            # Guard: only pop if still None -- forward-compat if a future oemof
            # release sets these to proper Pyomo Suffixes before calling solve.
            for _attr in ("dual", "rc"):
                if model.__dict__.get(_attr) is None:
                    model.__dict__.pop(_attr, None)

            solver_results = opt.solve(model, tee=config.output_verbose)

            # Mirror what oemof's model.solve() sets so downstream code works.
            model.solver_results = solver_results
            model.es.results = solver_results

        elif _is_glpk:
            solver_io = config.solver_io or "lp"
            glpk_cmdline: dict[str, Any] = {"mipgap": str(effective_mip_gap)}
            if effective_time_limit > 0:
                glpk_cmdline["tmlim"] = str(effective_time_limit)
            model.solve(
                solver=config.solver_name,
                solver_io=solver_io,
                allow_nonoptimal=True,
                solve_kwargs={"tee": config.output_verbose},
                cmdline_options=glpk_cmdline,
            )

        else:
            # CBC (default) and any other LP-file solver
            solver_io = config.solver_io or "lp"
            cbc_cmdline: dict[str, Any] = {"ratioGap": str(effective_mip_gap)}
            if effective_time_limit > 0:
                cbc_cmdline["sec"] = str(effective_time_limit)
            model.solve(
                solver=config.solver_name,
                solver_io=solver_io,
                allow_nonoptimal=True,
                solve_kwargs={"tee": config.output_verbose},
                cmdline_options=cbc_cmdline,
            )

    except (SolverError, SolverNotFoundError, SolverTimeLimitError, InfeasibleError):
        raise  # re-raise our own typed exceptions unchanged
    except Exception as exc:
        # This branch handles hard failures (solver not installed, Python
        # error, etc.) -- NOT non-optimal termination (that never raises when
        # allow_nonoptimal=True).
        msg = str(exc).lower()
        # HiGHS (appsi) raises RuntimeError("A feasible solution was not found
        # ...") when infeasible.  Check this BEFORE the generic "not found" test
        # so it isn't mis-classified as SolverNotFoundError.
        if "feasible solution was not found" in msg or "infeasible" in msg:
            raise InfeasibleError(
                f"Solver '{config.solver_name}' reported infeasibility: {exc}"
            ) from exc
        if (
            "not found" in msg
            or "executable" in msg
            or "applicationerror" in msg
            or "no solver" in msg
            or "notfound" in msg
            or "unavailable" in msg
        ):
            raise SolverNotFoundError(
                f"Solver '{config.solver_name}' not found. "
                "Install HiGHS with: pip install highspy  (recommended), "
                "or use: solver_name='cbc' (pip install coincbc)."
            ) from exc
        raise SolverError(f"Solver raised an unexpected error: {exc}") from exc

    # ------------------------------------------------------------------
    # 4. Inspect termination condition
    # ------------------------------------------------------------------
    tc = str(model.solver_results.Solver.Termination_condition).lower()
    status = str(model.solver_results.Solver.Status).lower()
    build_time = time.perf_counter() - t0
    log.info("Solver finished in %.1f s -- status=%r  tc=%r", build_time, status, tc)

    if "infeasible" in tc or "infeasible" in status:
        raise InfeasibleError(
            "Problem is infeasible. Check that there is sufficient generation "
            "capacity to meet demand (or relax max_lpsp > 0)."
        )
    # "maxtimelimit", "timelimit", "time" are all CBC / pyomo variants
    if "time" in tc:
        raise SolverTimeLimitError(
            f"Solver hit the time limit ({effective_time_limit} s) without "
            "finding an optimal solution. Increase time_limit_s or simplify "
            "the scenario."
        )
    if "optimal" not in tc:
        raise SolverError(
            f"Solver returned a non-optimal status: tc={tc!r}  status={status!r}. "
            "Check solver output for details."
        )

    # ------------------------------------------------------------------
    # 5. Return Results object
    # ------------------------------------------------------------------
    return solph.Results(model)
