# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Shared fixtures and helpers for the golden scenario benchmark suite.

The golden suite lives in ``tests/goldens/`` and is organised into one
subdirectory per scenario::

    tests/goldens/
    ├── conftest.py               ← this file
    ├── g01_grid_pv_batt/
    │   ├── scenario.yaml
    │   └── reference.json
    ├── g02_offgrid_pv_batt_dg/
    │   ├── scenario.yaml
    │   └── reference.json
    ...

All benchmark tests are tagged ``@pytest.mark.benchmark`` so they can be
selected or deselected without affecting the fast unit-test suite::

    pytest tests/goldens/ -v                       # run all golden tests
    pytest tests/ -m "not benchmark"               # skip golden tests
    pytest tests/goldens/ -m benchmark -v          # only golden tests
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from samba.scenario import load_scenario

if TYPE_CHECKING:
    from samba.scenario.models import Scenario

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GOLDENS_DIR: Path = Path(__file__).parent

#: Glob pattern that matches every golden-scenario directory (``gNN_*/``).
#: Uses ``g[0-9]*`` to cover two-digit indices g10, g11, g12 ... as well as g01–g09.
_SCENARIO_GLOB = "g[0-9]*"


# ---------------------------------------------------------------------------
# Public helpers used by test_golden.py
# ---------------------------------------------------------------------------


def golden_scenario_dirs() -> list[Path]:
    """Return sorted list of golden scenario directories.

    Each entry is a directory that contains both ``scenario.yaml`` and
    ``reference.json``.
    """
    dirs = sorted(GOLDENS_DIR.glob(_SCENARIO_GLOB))
    # Filter to directories that look complete (have both required files)
    return [d for d in dirs if d.is_dir() and (d / "scenario.yaml").exists()]


def load_reference(scenario_dir: Path) -> dict[str, Any]:
    """Load and parse ``reference.json`` from *scenario_dir*.

    Parameters
    ----------
    scenario_dir:
        Path to the golden scenario subdirectory.

    Returns
    -------
    dict
        Parsed JSON object containing ``"kpis"`` and ``"tolerances"`` keys.

    Raises
    ------
    FileNotFoundError
        If ``reference.json`` is missing.
    """
    ref_path = scenario_dir / "reference.json"
    if not ref_path.exists():
        raise FileNotFoundError(f"reference.json not found: {ref_path}")
    data: dict[str, Any] = json.loads(ref_path.read_text(encoding="utf-8"))
    return data


def load_golden_scenario(scenario_dir: Path) -> Scenario:
    """Load the SAMBA ``Scenario`` from ``scenario.yaml`` in *scenario_dir*."""
    return load_scenario(scenario_dir / "scenario.yaml")


# ---------------------------------------------------------------------------
# Tolerance assertion helper
# ---------------------------------------------------------------------------


def assert_within_tolerance(
    samba_kpis: dict[str, float],
    reference: dict,  # type: ignore[type-arg]
) -> None:
    """Assert that every KPI in *reference* is within the specified tolerance.

    Parameters
    ----------
    samba_kpis:
        A flat ``{kpi_name: value}`` dict produced by running SAMBA on the
        golden scenario (e.g. built from ``samba.run()`` results).
    reference:
        Parsed ``reference.json`` dict.  Must have ``"kpis"`` and
        ``"tolerances"`` sub-dicts.

    Raises
    ------
    AssertionError
        If any KPI deviates beyond its specified tolerance.  The error message
        includes the reference value, SAMBA value, and percentage deviation so
        failures are immediately actionable without digging through logs.
    """
    ref_kpis = reference["kpis"]
    tolerances = reference["tolerances"]

    failures: list[str] = []

    for kpi_name, ref_value in ref_kpis.items():
        if kpi_name not in tolerances:
            # No tolerance spec → skip comparison
            continue
        if kpi_name not in samba_kpis:
            failures.append(f"  {kpi_name}: SAMBA result missing (expected {ref_value})")
            continue

        samba_value = samba_kpis[kpi_name]
        tol_spec = tolerances[kpi_name]
        tol_type = tol_spec["type"]
        tol_value = tol_spec["value"]

        if tol_type == "relative":
            if ref_value == 0.0:
                # Avoid division by zero: treat as absolute comparison
                deviation = abs(samba_value - ref_value)
                passed = deviation <= tol_value
                deviation_str = f"abs deviation {deviation:.4f} (ref=0, tol={tol_value})"
            else:
                deviation = abs(samba_value - ref_value) / abs(ref_value)
                passed = deviation <= tol_value
                deviation_str = f"{deviation:.1%} deviation (tol={tol_value:.0%})"
        elif tol_type == "absolute":
            deviation = abs(samba_value - ref_value)
            passed = deviation <= tol_value
            deviation_str = f"abs deviation {deviation:.4f} (tol={tol_value})"
        else:
            raise ValueError(f"Unknown tolerance type: {tol_type!r}")

        if not passed:
            failures.append(
                f"  {kpi_name}: SAMBA={samba_value:.4f}  ref={ref_value:.4f}  {deviation_str}"
            )

    if failures:
        msg = "Golden KPI tolerance check FAILED:\n" + "\n".join(failures)
        raise AssertionError(msg)


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def goldens_dir() -> Path:
    """Return the path to the ``tests/goldens/`` directory."""
    return GOLDENS_DIR
