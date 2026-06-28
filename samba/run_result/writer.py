# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Artifact file writers for SAMBA run directories.

All writer functions follow the schema defined in
''docs/developer/results-contract.md''.  Column names and JSON field names are
authoritative from that document; do not rename them without updating the
contract.
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from samba.scenario.models import Scenario
    from samba.solver.runner import SolverConfig

log = logging.getLogger(__name__)

__all__ = [
    "build_metadata",
    "ensure_run_dir",
    "write_dispatch",
    "write_economics",
    "write_kpis",
    "write_metadata",
    "write_scenario",
    "write_sizing",
    "write_tariff",
]


# ---------------------------------------------------------------------------
# Directory management
# ---------------------------------------------------------------------------


def ensure_run_dir(base_dir: Path, scenario_name: str) -> Path:
    """Create and return a timestamped run directory.

    The directory is created at ''{base_dir}/{scenario_name}_{timestamp}/''
    where ''timestamp'' is ''YYYYMMDD_HHMMSS'' (UTC).

    Parameters
    ----------
    base_dir:
        Parent directory that will contain the run directory.
    scenario_name:
        Used as the directory name prefix.  Non-filesystem-safe characters are
        replaced with underscores.

    Returns
    -------
    Path
        Absolute path of the newly created run directory.
    """
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in scenario_name)
    ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    stem = f"{safe_name}_{ts}"
    attempt = 0
    while True:
        suffix = "" if attempt == 0 else f"_{attempt:02d}"
        run_dir = base_dir / f"{stem}{suffix}"
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            log.debug("Created run directory: %s", run_dir)
            return run_dir
        except FileExistsError:
            attempt += 1


# ---------------------------------------------------------------------------
# Dispatch writer
# ---------------------------------------------------------------------------


def write_dispatch(run_dir: Path, dispatch: pd.DataFrame) -> None:
    """Write the dispatch DataFrame to parquet and CSV.

    Files created:
     - ''{run_dir}/dispatch.parquet''  (snappy-compressed, pyarrow engine)
     - ''{run_dir}/dispatch.csv''      (UTF-8, index written as "timestamp")

    Parameters
    ----------
    run_dir:
        Target run directory (must exist).
    dispatch:
        8 760-row DataFrame from :func:'~samba.solver.extract.extract_dispatch'.
        Index must be named ''"timestamp"''.
    """
    parquet_path = run_dir / "dispatch.parquet"
    csv_path = run_dir / "dispatch.csv"

    dispatch.to_parquet(parquet_path, engine="pyarrow", compression="snappy")
    dispatch.to_csv(csv_path)

    log.debug("Wrote dispatch: %s  and  %s", parquet_path, csv_path)


# ---------------------------------------------------------------------------
# Metadata writer
# ---------------------------------------------------------------------------


def build_metadata(
    scenario: Scenario,
    solver_config: SolverConfig,
    solve_time_s: float,
    solver_results: Any = None,
    *,
    run_id: str,
) -> dict[str, Any]:
    """Build and return the metadata dictionary for a run."""

    # Scenario hash: SHA-256 of the serialised scenario JSON
    try:
        scenario_bytes = scenario.model_dump_json(indent=None).encode()
        scenario_hash = "sha256:" + hashlib.sha256(scenario_bytes).hexdigest()
    except Exception:  # noqa: BLE001
        scenario_hash = "unknown"

    # Git hash (best-effort)
    git_hash = _git_hash()

    # oemof-solph version
    oemof_version = _package_version("oemof.solph")

    # Solver status / termination from raw Pyomo results
    status = "optimal"
    solver_status = "ok"
    solver_termination = "optimal"
    if solver_results is not None:
        try:
            solver_status = str(solver_results.Solver.Status)
            solver_termination = str(solver_results.Solver.Termination_condition)
            status = "optimal" if "optimal" in solver_termination.lower() else "non-optimal"
        except Exception:  # noqa: BLE001
            pass

    return {
        "run_id": run_id,
        "samba_version": _package_version("samba"),
        "git_hash": git_hash,
        "timestamp_utc": datetime.now(tz=UTC).isoformat(),
        "wall_time_seconds": round(solve_time_s, 3),
        "solver": {
            "name": solver_config.solver_name,
            "version": "unknown",  # solver version not exposed by pyomo easily
        },
        "oemof_solph_version": oemof_version,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "kpis_schema_version": 1,
        "scenario_hash": scenario_hash,
        "status": status,
        "solver_status": solver_status,
        "solver_termination": solver_termination,
    }


def write_metadata(
    run_dir: Path,
    scenario: Scenario,
    solver_config: SolverConfig,
    solve_time_s: float,
    solver_results: Any = None,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Write ''metadata.json'' to *run_dir* and return the metadata dict.

    Parameters
    ----------
    run_dir:
        Target run directory (must exist).
    scenario:
        Validated scenario -- used to compute the scenario hash and to record
        the scenario name.
    solver_config:
        Solver configuration used for the run.
    solve_time_s:
        Total wall-clock solve time in seconds.
    solver_results:
        Optional raw Pyomo solver results object (used to read solver status
        and termination condition).  May be ''None'' for tests.
    run_id:
        Override the run ID.  Defaults to the directory name.

    Returns
    -------
    dict[str, Any]
        The metadata dictionary written to disk.
    """
    resolved_run_id = run_id or run_dir.name
    metadata = build_metadata(
        scenario=scenario,
        solver_config=solver_config,
        solve_time_s=solve_time_s,
        solver_results=solver_results,
        run_id=resolved_run_id,
    )

    out_path = run_dir / "metadata.json"
    out_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    log.debug("Wrote metadata: %s", out_path)
    return metadata


# ---------------------------------------------------------------------------
# KPI and economics writers
# ---------------------------------------------------------------------------


def write_kpis(run_dir: Path, kpis: dict[str, Any]) -> None:
    """Write ''kpis.json'' to *run_dir*.

    Parameters
    ----------
    run_dir:
        Target run directory (must exist).
    kpis:
        KPI dictionary from :func:'~samba.run_result.kpis.compute_kpis'.
    """
    out_path = run_dir / "kpis.json"
    out_path.write_text(json.dumps(kpis, indent=2), encoding="utf-8")
    log.debug("Wrote kpis: %s", out_path)


def write_economics(run_dir: Path, economics: dict[str, Any]) -> None:
    """Write ''economics.json'' to *run_dir*.

    Parameters
    ----------
    run_dir:
        Target run directory (must exist).
    economics:
        Economics dictionary from :func:'~samba.run_result.kpis.compute_kpis'.
    """
    out_path = run_dir / "economics.json"
    out_path.write_text(json.dumps(economics, indent=2), encoding="utf-8")
    log.debug("Wrote economics: %s", out_path)


def write_sizing(run_dir: Path, sizing: pd.DataFrame) -> None:
    """Write ''sizing.csv'' to *run_dir*.

    Parameters
    ----------
    run_dir:
        Target run directory (must exist).
    sizing:
        Sizing DataFrame from :func:'~samba.run_result.kpis.compute_kpis'.
        Columns: ''component'', ''capacity'', ''unit'', ''count'',
        ''capital_cost''.
    """
    out_path = run_dir / "sizing.csv"
    sizing.to_csv(out_path, index=False)
    log.debug("Wrote sizing: %s", out_path)


def write_tariff(run_dir: Path, tariff_arrays: Any) -> None:
    """Write tariff arrays to ''tariff.parquet'' in *run_dir*.

    The tariff is stored as a DataFrame with columns ''cbuy'' (hourly buy
    price, $/kWh), ''csell'' (hourly sell price, $/kWh), and ''service_charge''
    (monthly service charge, padded to 8 760 rows for uniform storage).

    Parameters
    ----------
    run_dir:
        Target run directory (must exist).
    tariff_arrays:
        :class:'~samba.tariff.resolver.TariffArrays' instance.
    """
    import numpy as np

    cbuy = getattr(tariff_arrays, "cbuy", None)
    csell = getattr(tariff_arrays, "csell", None)
    service_charge = getattr(tariff_arrays, "service_charge", None)

    # cbuy / csell are 8760-length arrays; service_charge is 12-length.
    # Store all three columns in an 8760-row parquet.
    n = 8760
    cbuy_arr = np.asarray(cbuy, dtype=float) if cbuy is not None else np.zeros(n)
    csell_arr = np.asarray(csell, dtype=float) if csell is not None else np.zeros(n)

    # Expand monthly service_charge to hourly (repeat for days-in-month).
    if service_charge is not None:
        sc_monthly = np.asarray(service_charge, dtype=float)
        # Broadcast: assign each month's value to all 8760 hours.
        hours_per_month = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
        sc_hourly = np.repeat(sc_monthly, hours_per_month[: len(sc_monthly)])
        # Clip/pad to exactly 8760
        if len(sc_hourly) > n:
            sc_hourly = sc_hourly[:n]
        elif len(sc_hourly) < n:
            sc_hourly = np.pad(sc_hourly, (0, n - len(sc_hourly)))
    else:
        sc_hourly = np.zeros(n)

    df = pd.DataFrame(
        {"cbuy": cbuy_arr[:n], "csell": csell_arr[:n], "service_charge_expanded": sc_hourly}
    )
    out_path = run_dir / "tariff.parquet"
    df.to_parquet(out_path, engine="pyarrow", compression="snappy")
    log.debug("Wrote tariff: %s", out_path)


def write_scenario(run_dir: Path, scenario: Scenario) -> None:
    """Write the scenario to ''scenario.json'' in *run_dir*.

    Parameters
    ----------
    run_dir:
        Target run directory (must exist).
    scenario:
        The validated :class:'~samba.scenario.models.Scenario' instance.
    """
    out_path = run_dir / "scenario.json"
    out_path.write_text(scenario.model_dump_json(indent=2), encoding="utf-8")
    log.debug("Wrote scenario: %s", out_path)


def _git_hash() -> str:
    """Return the current git commit hash, or ''"unknown"'' if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def _package_version(package: str) -> str:
    """Return the installed package version string."""
    try:
        from importlib.metadata import version

        return version(package)
    except Exception:  # noqa: BLE001
        return "unknown"
