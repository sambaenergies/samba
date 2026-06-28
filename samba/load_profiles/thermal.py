# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Thermal load profile generation for Phase 22.

Supports two loading strategies:

* **CSV** – load hourly kW_th arrays directly from single-column CSV files.
* **Degree-day** – derive heating/cooling demand from outdoor ambient
  temperature and a building heat-loss coefficient (UA value).

The :func:`load_thermal_loads` function is the single entry point used by the
compiler and by :func:`~samba.compiler.compiler.precompute_thermal_peaks`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from samba.scenario.models import ThermalLoad

log = logging.getLogger(__name__)

__all__ = ["ThermalLoads", "load_thermal_loads"]

_HOURS_PER_YEAR = 8760


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------


@dataclass
class ThermalLoads:
    """Hourly heating and cooling demand arrays at the supply side [kW_th].

    For CSV sources the arrays are read verbatim from the supplied files.
    For the degree-day model the arrays are already scaled for supply-side
    use (i.e. divided by ``distribution_efficiency``).

    Attributes
    ----------
    heating:
        Shape ``(8760,)`` float64, hourly heating demand [kW_th].
    cooling:
        Shape ``(8760,)`` float64, hourly cooling demand [kW_th].
    """

    heating: np.ndarray  # (8760,) kW_th
    cooling: np.ndarray  # (8760,) kW_th

    @property
    def peak_heating_kw(self) -> float:
        """Maximum hourly heating demand [kW_th]."""
        return float(self.heating.max()) if len(self.heating) > 0 else 0.0

    @property
    def peak_cooling_kw(self) -> float:
        """Maximum hourly cooling demand [kW_th]."""
        return float(self.cooling.max()) if len(self.cooling) > 0 else 0.0

    @property
    def annual_heating_kwh_th(self) -> float:
        """Total annual heating energy [kWh_th]."""
        return float(self.heating.sum())

    @property
    def annual_cooling_kwh_th(self) -> float:
        """Total annual cooling energy [kWh_th]."""
        return float(self.cooling.sum())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_single_csv(path: str | Path) -> np.ndarray:
    """Load the first column of *path* as a float64 array of length 8760.

    The CSV must have exactly one header row followed by 8760 rows of numeric
    data (same convention as test helpers and documentation examples).
    """
    arr: np.ndarray = pd.read_csv(path).iloc[:, 0].to_numpy(dtype=float)
    if len(arr) != _HOURS_PER_YEAR:
        raise ValueError(f"Thermal CSV '{path}' must have {_HOURS_PER_YEAR} rows; got {len(arr)}.")
    if np.any(arr < 0.0):
        raise ValueError(f"Thermal CSV '{path}' contains negative values.")
    return arr


def _load_csv(heating_path: str | None, cooling_path: str | None) -> ThermalLoads:
    """Load heating and/or cooling profiles from CSV files."""
    heating = (
        _read_single_csv(heating_path)
        if heating_path is not None
        else np.zeros(_HOURS_PER_YEAR, dtype=float)
    )
    cooling = (
        _read_single_csv(cooling_path)
        if cooling_path is not None
        else np.zeros(_HOURS_PER_YEAR, dtype=float)
    )
    log.debug(
        "Loaded thermal CSV profiles: heating peak=%.1f kW, cooling peak=%.1f kW",
        heating.max(),
        cooling.max(),
    )
    return ThermalLoads(heating=heating, cooling=cooling)


def _degree_day_loads(
    t_outdoor: np.ndarray,
    ua_heat: float,
    ua_cool: float,
    t_set_heat: float,
    t_set_cool: float,
    eta_dist: float,
) -> ThermalLoads:
    """Compute hourly heating/cooling demand from outdoor temperature and UA.

    Heating demand::

        q_heat[t] = UA_heat * max(t_set_heat - T_out[t], 0) / eta_dist

    Cooling demand::

        q_cool[t] = UA_cool * max(T_out[t] - t_set_cool, 0) / eta_dist

    Parameters
    ----------
    t_outdoor:
        Hourly outdoor temperature array [°C], shape (8760,).
    ua_heat:
        Building heat-loss coefficient for heating [kW/K].
    ua_cool:
        Building heat-gain coefficient for cooling [kW/K].
    t_set_heat:
        Heating setpoint temperature [°C].
    t_set_cool:
        Cooling setpoint temperature [°C].
    eta_dist:
        Distribution system efficiency (0, 1].  Demand is divided by this
        value so the supply-side output needed from the heat pump / boiler is
        correctly uplifted for pipe/duct losses.

    Returns
    -------
    ThermalLoads
        Supply-side demand arrays [kW_th].
    """
    if len(t_outdoor) != _HOURS_PER_YEAR:
        raise ValueError(f"t_outdoor must have {_HOURS_PER_YEAR} elements; got {len(t_outdoor)}.")
    heating = ua_heat * np.maximum(t_set_heat - t_outdoor, 0.0) / eta_dist
    cooling = ua_cool * np.maximum(t_outdoor - t_set_cool, 0.0) / eta_dist
    log.debug(
        "Degree-day thermal loads: heating peak=%.1f kW, cooling peak=%.1f kW",
        heating.max(),
        cooling.max(),
    )
    return ThermalLoads(heating=heating, cooling=cooling)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_thermal_loads(
    thermal: ThermalLoad,
    t_outdoor: np.ndarray | None = None,
    *,
    base_dir: Path | None = None,
) -> ThermalLoads:
    """Compute hourly thermal load profiles from a :class:`.ThermalLoad` config.

    Parameters
    ----------
    thermal:
        Validated ``ThermalLoad`` configuration from the scenario.
    t_outdoor:
        Hourly outdoor temperature array [°C], shape (8760,).  Required when
        ``thermal.source == 'degree_day'``; ignored for ``'csv'`` sources.
    base_dir:
        Base directory used to resolve relative CSV paths declared in
        ``thermal.heating_csv_path`` / ``thermal.cooling_csv_path``.  When
        ``None`` the paths are used as-is (absolute or relative to CWD).

    Returns
    -------
    ThermalLoads
        Supply-side heating and cooling demand arrays [kW_th].

    Raises
    ------
    ValueError
        If required fields are missing or array dimensions are wrong.
    """
    if thermal.source == "csv":

        def _resolve(p: str | None) -> str | None:
            if p is None:
                return None
            resolved = Path(p)
            if base_dir is not None and not resolved.is_absolute():
                resolved = base_dir / resolved
            return str(resolved)

        return _load_csv(_resolve(thermal.heating_csv_path), _resolve(thermal.cooling_csv_path))

    # degree_day branch
    if t_outdoor is None:
        raise ValueError(
            "t_outdoor (hourly outdoor temperature) is required when "
            "ThermalLoad.source='degree_day'."
        )
    ua_heat = float(thermal.building_ua_kw_per_k)  # type: ignore[arg-type]
    ua_cool = float(
        thermal.building_ua_cool_kw_per_k
        if thermal.building_ua_cool_kw_per_k is not None
        else ua_heat
    )
    return _degree_day_loads(
        t_outdoor=np.asarray(t_outdoor, dtype=float),
        ua_heat=ua_heat,
        ua_cool=ua_cool,
        t_set_heat=thermal.heating_setpoint_c,
        t_set_cool=thermal.cooling_setpoint_c,
        eta_dist=thermal.distribution_efficiency,
    )
