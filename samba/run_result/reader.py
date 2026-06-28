# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Result reader for SAMBA run directories.

Provides a :class:'RunResult' dataclass and the :func:'load_result' loader
that reconstructs all result artifacts from a previously written run directory.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["RunResult", "load_result"]


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """All result artifacts loaded from a SAMBA run directory.

    Attributes
    ----------
    run_dir:
        Absolute path to the run directory that was loaded.
    metadata:
        Contents of ''metadata.json'' as a plain dict.
    kpis:
        Contents of ''kpis.json'' as a plain dict.  Contains all 28 KPI
        fields defined in ''docs/developer/results-contract.md''.
    dispatch:
        8 760-row dispatch DataFrame loaded from ''dispatch.parquet''
        (falls back to ''dispatch.csv'' if parquet is absent).
    economics:
        Contents of ''economics.json'' as a plain dict.
    sizing:
        ''sizing.csv'' loaded as a DataFrame with columns ''component'',
        ''capacity'', ''unit'', ''count'', ''capital_cost''.
    scenario_raw:
        Raw JSON dict loaded from ''scenario.json''.  May be ''None'' if the
        file was not written (e.g. legacy run directories).
    """

    run_dir: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    kpis: dict[str, Any] = field(default_factory=dict)
    dispatch: pd.DataFrame = field(default_factory=pd.DataFrame)
    economics: dict[str, Any] = field(default_factory=dict)
    sizing: pd.DataFrame = field(default_factory=pd.DataFrame)
    scenario_raw: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def npc(self) -> float:
        """Net Present Cost in project currency."""
        return float(self.kpis.get("npc", float("nan")))

    @property
    def lcoe(self) -> float:
        """Levelised Cost of Energy in $/kWh."""
        return float(self.kpis.get("lcoe", float("nan")))

    @property
    def renewable_fraction(self) -> float:
        """Fraction of total generation from renewables (0-1)."""
        return float(self.kpis.get("renewable_fraction", float("nan")))

    @property
    def lpsp(self) -> float:
        """Loss of Power Supply Probability (0-1)."""
        return float(self.kpis.get("lpsp", float("nan")))

    @property
    def scenario(self) -> Scenario | None:
        """The run's scenario as a typed :class:`~samba.scenario.models.Scenario`.

        Lazily deserialised from :attr:`scenario_raw` (cached after first
        access); ``None`` if the run directory did not include ``scenario.json``.
        Prefer this over :attr:`scenario_raw` for IDE completion and validation.
        """
        if self.scenario_raw is None:
            return None
        cached = self.__dict__.get("_scenario")
        if cached is None:
            from samba.scenario.models import Scenario

            cached = Scenario.model_validate(self.scenario_raw)
            self.__dict__["_scenario"] = cached
        return cached

    def __repr__(self) -> str:  # pragma: no cover
        npc = self.kpis.get("npc", "?")
        lcoe = self.kpis.get("lcoe", "?")
        return f"RunResult(run_dir={self.run_dir.name!r}, npc={npc}, lcoe={lcoe})"


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_result(run_dir: Path | str) -> RunResult:
    """Load all result artifacts from a SAMBA run directory.

    Missing optional files produce empty defaults rather than raising
    exceptions, so the function is robust to partial runs.

    Parameters
    ----------
    run_dir:
        Path to the run directory (e.g. ''outputs/my_scenario_20240101_120000'').

    Returns
    -------
    RunResult
        Fully populated result container.

    Raises
    ------
    FileNotFoundError
        If *run_dir* does not exist.
    """
    run_dir = Path(run_dir).resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    metadata = _load_json(run_dir / "metadata.json")
    kpis = _load_json(run_dir / "kpis.json")
    economics = _load_json(run_dir / "economics.json")
    scenario_raw = _load_json(run_dir / "scenario.json") or None
    dispatch = _load_dispatch(run_dir)
    sizing = _load_sizing(run_dir)

    log.debug("Loaded RunResult from %s", run_dir)
    return RunResult(
        run_dir=run_dir,
        metadata=metadata,
        kpis=kpis,
        dispatch=dispatch,
        economics=economics,
        sizing=sizing,
        scenario_raw=scenario_raw,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    """Return parsed JSON dict, or empty dict on any failure."""
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(result, dict):
            return result
        return {}
    except Exception:  # noqa: BLE001
        log.debug("Could not load %s (may not exist)", path)
        return {}


def _load_dispatch(run_dir: Path) -> pd.DataFrame:
    """Load dispatch.parquet (preferred) or dispatch.csv (fallback)."""
    parquet = run_dir / "dispatch.parquet"
    csv = run_dir / "dispatch.csv"
    try:
        df = pd.read_parquet(parquet, engine="pyarrow")
        log.debug("Loaded dispatch from parquet (%d rows)", len(df))
        return df
    except Exception:  # noqa: BLE001
        pass
    try:
        df = pd.read_csv(csv, index_col="timestamp", parse_dates=True)
        log.debug("Loaded dispatch from CSV (%d rows)", len(df))
        return df
    except Exception:  # noqa: BLE001
        log.debug("dispatch file not found in %s", run_dir)
        return pd.DataFrame()


def _load_sizing(run_dir: Path) -> pd.DataFrame:
    """Load sizing.csv, returning empty DataFrame on failure."""
    path = run_dir / "sizing.csv"
    try:
        return pd.read_csv(path)
    except Exception:  # noqa: BLE001
        log.debug("sizing.csv not found in %s", run_dir)
        return pd.DataFrame()
