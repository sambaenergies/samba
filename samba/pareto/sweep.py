# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Weighted-sum Pareto front sweep for cost-emissions trade-offs.

.. warning::

   The ''samba pareto'' sweep generates a **weighted-sum approximation** of
   the Pareto front -- one solution per alpha (carbon price) value.  This is NOT a
   true Pareto-efficient set; non-convex regions of the true Pareto frontier
   can be missed.  The results are suitable for sensitivity analysis and
   scenario comparison, but should not be presented as an exact Pareto front
   in publications without this qualification.

Running N points at ~1-5 min each means a 10-point sweep takes 10-50 minutes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import numpy as np

log = logging.getLogger(__name__)

__all__ = [
    "ParetoPoint",
    "default_alpha_range",
    "run_pareto_sweep",
    "run_pareto_sweep_epsilon",
]


@dataclass
class ParetoPoint:
    """A single point on the weighted-sum Pareto approximation.

    Attributes
    ----------
    alpha:
        Carbon price used for this run [$/kg CO2].  ''0.0'' = cost-only.
    npc:
        Net Present Cost [$].
    lem:
        Levelised Emissions Metric [kg CO2 / kWh delivered].
    total_emissions_kg:
        Total annual CO2-equivalent emissions [kg/yr].
    sizing:
        Dict of component capacities: ''pv_kw'', ''battery_kwh'',
        ''battery_kw'', ''inverter_kw'', ''wt_kw'', ''dg_kw''.
    run_dir:
        Path to the artifact directory for this point (or ''Path(".")'' when
        *output_dir* was ''None'').
    dominated:
        ''True'' when this point is dominated by another in the sweep set.
        Set by :func:'run_pareto_sweep' after all points are collected.
    """

    alpha: float
    npc: float
    lem: float
    total_emissions_kg: float
    sizing: dict[str, float] = field(default_factory=dict)
    run_dir: Path = field(default_factory=lambda: Path("."))
    dominated: bool = False
    # emissions cap for epsilon-constraint points (None = weighted-sum point)
    epsilon: float | None = None


def default_alpha_range(n_points: int = 10) -> list[float]:
    """Return a list of *n_points* alpha values suitable for a Pareto sweep.

    The range starts at ''0.0'' (cost-only) and continues with
    ''n_points - 1'' log-spaced values from ''0.001'' to ''50.0''
    [$/kg CO2].  Log-spacing concentrates points near the cost-optimal
    end where the transition from cost-only to emissions-penalised
    behaviour occurs.

    Parameters
    ----------
    n_points:
        Total number of alpha values including the ''0.0'' point.

    Returns
    -------
    list[float]
    """
    if n_points < 1:
        raise ValueError("n_points must be >= 1")
    if n_points == 1:
        return [0.0]
    tail = list(np.logspace(np.log10(0.001), np.log10(50.0), n_points - 1))
    return [0.0] + tail


def run_pareto_sweep(
    scenario: object,  # samba.scenario.models.Scenario
    load_kw: np.ndarray,
    alphas: list[float],
    run_base_dir: Path | str | None = None,
    pv_per_kwp: np.ndarray | None = None,
    wind_power_kw: np.ndarray | None = None,
    config: object | None = None,  # samba.solver.runner.SolverConfig
    progress_callback: Callable[[int, int, float], None] | None = None,
    scenario_dir: Path | str | None = None,
) -> list[ParetoPoint]:
    """Run SAMBA for each alpha value in *alphas* and return colected Pareto points.

    Each call resolves the tariff arrays once from the base scenario, then
    loops over *alphas*, overriding ''scenario.objective.emissions_weight''
    for each solve.  Arrays (load, PV, wind) are reused across calls.

    Parameters
    ----------
    scenario:
        Validated :class:'~samba.scenario.models.Scenario' base case.
    load_kw:
        Hourly load profile [kW], shape ''(8760,)''.
    alphas:
        Ordered list of carbon prices [$/kg CO2].  Include ''0.0'' to
        capture the cost-only reference point.
    run_base_dir:
        If given, artifact directories are written under this path (one
        sub-directory per alpha point).  ''None'' = in-memory only.
    pv_per_kwp:
        Normalised PV output per kWp [fraction], shape ''(8760,)'' or
        ''None'' if no PV component.
    wind_power_kw:
        Per-turbine wind power [kW], shape ''(8760,)'' or ''None'' if no
        wind component.
    config:
        :class:'~samba.solver.runner.SolverConfig' instance or ''None''
        (uses the default HiGHS configuration).
    progress_callback:
        Optional ''(point_index, total_points, alpha) -> None'' callable
        invoked before each solve for progress reporting.

    Returns
    -------
    list[ParetoPoint]
        All collected points, sorted by NPC ascending.  The ''dominated''
        flag is set on each point: a point is dominated if there exists
        another point with strictly lower NPC **and** strictly lower LEM.
    """
    import samba
    from samba.scenario.models import Objective
    from samba.solver.runner import SolverConfig

    solver_config: SolverConfig | None = cast("SolverConfig | None", config)

    run_base = Path(run_base_dir) if run_base_dir is not None else None

    points: list[ParetoPoint] = []
    n = len(alphas)

    for i, alpha in enumerate(alphas):
        if progress_callback is not None:
            progress_callback(i, n, alpha)

        log.info("Pareto sweep: point %d/%d  alpha=%.4f $/kg CO2", i + 1, n, alpha)

        # Build modified scenario: override objective only
        if alpha > 0.0:
            modified_obj = Objective(type="cost_and_emissions", emissions_weight=alpha)
        else:
            modified_obj = Objective(type="cost", emissions_weight=alpha)
        modified_scenario = scenario.model_copy(update={"objective": modified_obj})  # type: ignore[attr-defined]

        # Determine per-point output directory
        point_dir: Path | None = None
        if run_base is not None:
            alpha_label = f"alpha_{alpha:.6g}".replace(".", "_")
            point_dir = run_base / alpha_label

        try:
            result = samba.run(
                modified_scenario,
                load_kw=load_kw,
                pv_per_kwp=pv_per_kwp,
                wind_power_kw=wind_power_kw,
                output_dir=point_dir,
                config=solver_config,
                scenario_dir=scenario_dir,
            )
        except Exception:
            log.exception("Pareto sweep: point %d (alpha=%.4g) failed -- skipping", i + 1, alpha)
            continue

        # Extract sizing dict from the sizing DataFrame
        sizing_dict: dict[str, float] = {}
        if result.sizing is not None and not result.sizing.empty:
            for _, row in result.sizing.iterrows():
                comp: str = str(row["component"])
                sizing_dict[comp] = float(row["capacity"])

        point = ParetoPoint(
            alpha=alpha,
            npc=result.kpis.get("npc", float("inf")),
            lem=result.kpis.get("lem", 0.0),
            total_emissions_kg=result.kpis.get("total_emissions_kg", 0.0),
            sizing=sizing_dict,
            run_dir=result.run_dir or Path("."),
        )
        points.append(point)
        log.info(
            "  NPC=%.2f  LEM=%.4f kg/kWh  emissions=%.1f kg/yr",
            point.npc,
            point.lem,
            point.total_emissions_kg,
        )

    # Sort by NPC ascending, then mark dominated points
    points.sort(key=lambda p: p.npc)
    _mark_dominated(points)
    return points


def run_pareto_sweep_epsilon(
    scenario: object,  # samba.scenario.models.Scenario
    load_kw: np.ndarray,
    n_points: int = 10,
    run_base_dir: Path | str | None = None,
    pv_per_kwp: np.ndarray | None = None,
    wind_power_kw: np.ndarray | None = None,
    config: object | None = None,  # samba.solver.runner.SolverConfig
    progress_callback: Callable[[int, int, float], None] | None = None,
    scenario_dir: Path | str | None = None,
) -> list[ParetoPoint]:
    """Trace the Pareto front by the **epsilon-constraint** method.

    Unlike :func:`run_pareto_sweep` (weighted-sum, convex-hull only), this caps
    annual emissions at a series of thresholds and minimises cost subject to each
    cap, so it can recover **non-convex** regions of the true frontier.

    The two endpoints are found first: a cost-only solve (max emissions, min cost)
    and a strongly emissions-weighted solve (min achievable emissions). The cap is
    then swept linearly between them; each interior point is a cost-minimising solve
    with ``constraints.max_total_emissions_kg = epsilon``.

    Note: the LP cap uses the LP-expressible emissions (grid + diesel fuel *slope*);
    the reported ``total_emissions_kg`` additionally includes the diesel no-load
    *intercept*, so for diesel systems the reported value may slightly exceed the
    cap. For grid + renewable systems the cap is exact.

    Returns the collected points sorted by NPC ascending (``dominated`` flagged).
    """
    import samba
    from samba.scenario.models import Objective
    from samba.solver.runner import SolverConfig

    if n_points < 2:
        raise ValueError("epsilon sweep needs n_points >= 2 (two endpoints)")

    solver_config: SolverConfig | None = cast("SolverConfig | None", config)
    run_base = Path(run_base_dir) if run_base_dir is not None else None
    sc: Any = scenario

    def _solve(modified: Any, label: str, epsilon: float | None) -> ParetoPoint | None:
        point_dir = run_base / label if run_base is not None else None
        try:
            result = samba.run(
                modified,
                load_kw=load_kw,
                pv_per_kwp=pv_per_kwp,
                wind_power_kw=wind_power_kw,
                output_dir=point_dir,
                config=solver_config,
                scenario_dir=scenario_dir,
            )
        except Exception:
            log.exception("Epsilon sweep: solve %r failed -- skipping", label)
            return None
        sizing_dict: dict[str, float] = {}
        if result.sizing is not None and not result.sizing.empty:
            for _, row in result.sizing.iterrows():
                sizing_dict[str(row["component"])] = float(row["capacity"])
        return ParetoPoint(
            alpha=0.0,
            npc=result.kpis.get("npc", float("inf")),
            lem=result.kpis.get("lem", 0.0),
            total_emissions_kg=result.kpis.get("total_emissions_kg", 0.0),
            sizing=sizing_dict,
            run_dir=result.run_dir or Path("."),
            epsilon=epsilon,
        )

    # Endpoint 1: cost-only (max emissions / min cost)
    if progress_callback is not None:
        progress_callback(0, n_points, 0.0)
    cost_only = sc.model_copy(update={"objective": Objective(type="cost")})
    p_cost = _solve(cost_only, "epsilon_cost_only", None)

    # Endpoint 2: strongly emissions-weighted (min achievable emissions)
    if progress_callback is not None:
        progress_callback(1, n_points, 0.0)
    min_emis_obj = Objective(type="cost_and_emissions", emissions_weight=1.0e6)
    min_emis = sc.model_copy(update={"objective": min_emis_obj})
    p_min = _solve(min_emis, "epsilon_min_emissions", None)

    points: list[ParetoPoint] = [p for p in (p_cost, p_min) if p is not None]

    # Interior caps swept between the two endpoints' emissions.
    if p_cost is not None and p_min is not None and n_points > 2:
        e_high = p_cost.total_emissions_kg
        e_low = p_min.total_emissions_kg
        if e_high > e_low:
            interior = np.linspace(e_low, e_high, n_points)[1:-1]
            base_constraints = sc.constraints
            for i, eps in enumerate(interior):
                if progress_callback is not None:
                    progress_callback(i + 2, n_points, float(eps))
                new_constraints = base_constraints.model_copy(
                    update={"max_total_emissions_kg": float(eps)}
                )
                modified = sc.model_copy(
                    update={
                        "objective": Objective(type="cost"),
                        "constraints": new_constraints,
                    }
                )
                pt = _solve(modified, f"epsilon_{eps:.6g}".replace(".", "_"), float(eps))
                if pt is not None:
                    points.append(pt)

    points.sort(key=lambda p: p.npc)
    _mark_dominated(points)
    return points


def write_pareto_results(points: list[ParetoPoint], output_path: Path | str) -> None:
    """Write ''pareto_front.csv'' and ''pareto_front.json'' to *output_path*.

    Parameters
    ----------
    points:
        List of :class:'ParetoPoint' objects from :func:'run_pareto_sweep'.
    output_path:
        Directory where the output files are written (created if missing).
    """
    import json

    import pandas as pd

    out = Path(output_path)
    out.mkdir(parents=True, exist_ok=True)

    rows = [
        {
            "alpha": p.alpha,
            "epsilon": p.epsilon,
            "npc": p.npc,
            "lem": p.lem,
            "total_emissions_kg": p.total_emissions_kg,
            "dominated": p.dominated,
            "run_dir": str(p.run_dir),
            **{f"size_{k}": v for k, v in p.sizing.items()},
        }
        for p in points
    ]
    df = pd.DataFrame(rows)
    df.to_csv(out / "pareto_front.csv", index=False)

    json_data = [
        {
            "alpha": p.alpha,
            "epsilon": p.epsilon,
            "npc": p.npc,
            "lem": p.lem,
            "total_emissions_kg": p.total_emissions_kg,
            "dominated": p.dominated,
            "sizing": p.sizing,
            "run_dir": str(p.run_dir),
        }
        for p in points
    ]
    (out / "pareto_front.json").write_text(json.dumps(json_data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _mark_dominated(points: list[ParetoPoint]) -> None:
    """Set ''point.dominated = True'' when another point has lower NPC and LEM.

    Assumes *points* is already sorted by NPC ascending.  Under that ordering,
    a point ''p[i]'' is dominated iff there exists some ''p[j]'' with
    ''j < i'' (lower NPC) and ''p[j].lem <= p[i].lem''.
    """
    min_lem_seen = float("inf")
    for p in points:
        if p.lem >= min_lem_seen:
            p.dominated = True
        else:
            min_lem_seen = p.lem
