# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Expand a :class:'~samba.scenario.models.Load' configuration to an 8 760-element
hourly kW array, across all ''Load.source'' variants in the scenario schema.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

from samba.load_profiles.generic import (
    build_generic_load_from_annual_total,
    build_generic_load_from_monthly,
    build_generic_load_normalized,
)
from samba.scenario.models import Load

# Standard non-leap-year month lengths used throughout SAMBA v1.
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
HOURS_IN_YEAR = 8760


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_csv_1d(path: pathlib.Path, expected_rows: int | None) -> np.ndarray:
    """Read a single-column CSV.  Raises ''ValueError'' if row count mismatches."""
    df = pd.read_csv(path, header=None)
    if df.shape[1] != 1:
        # Allow first column only if there are extra columns
        arr = df.iloc[:, 0].to_numpy(dtype=np.float64)
    else:
        arr = df.iloc[:, 0].to_numpy(dtype=np.float64)
    if expected_rows is not None and len(arr) != expected_rows:
        raise ValueError(f"CSV '{path}' must have exactly {expected_rows} rows; found {len(arr)}.")
    return np.asarray(arr, dtype=np.float64)


def _resolve_csv_path(csv_path: str, base_dir: pathlib.Path | None) -> pathlib.Path:
    """Resolve a CSV path, optionally relative to a base directory."""
    p = pathlib.Path(csv_path)
    if not p.is_absolute() and base_dir is not None:
        p = base_dir / p
    return p


def _expand_monthly_averages(monthly_avg_kw: np.ndarray) -> np.ndarray:
    """Expand 12 monthly-average kW values to 8 760 hourly values.

    Each month's average is repeated for every hour of that month.
    """
    result = np.empty(HOURS_IN_YEAR, dtype=np.float64)
    idx = 0
    for m, days in enumerate(DAYS_IN_MONTH):
        hours = 24 * days
        result[idx : idx + hours] = monthly_avg_kw[m]
        idx += hours
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def expand_load(
    load: Load,
    base_dir: pathlib.Path | None = None,
    peak_month: str = "January",
) -> np.ndarray:
    """Produce an 8 760-element hourly load array [kW] from a :class:'Load' spec.

    Parameters
    ----------
    load:
        Validated :class:'~samba.scenario.models.Load' model.
    base_dir:
        Directory used to resolve relative ''csv_path'' values.  Typically the
        directory containing the scenario YAML file.
    peak_month:
        Generic profile peak month: ''"July"'' (summer) or ''"January"'' (winter).
        Only used for ''generic_*'' source types.

    Returns
    -------
    np.ndarray, shape (8760,)
        Hourly electrical load [kW], all values >= 0.

    Raises
    ------
    ValueError
        If required parameters are missing or a CSV contains the wrong number of rows.
    NotImplementedError
        If the source type is not yet implemented.
    """
    result = _dispatch(load, base_dir, peak_month)

    # Apply scale factor and clip negatives
    arr: np.ndarray = np.maximum(result * load.scale_factor, 0.0)

    if len(arr) != HOURS_IN_YEAR:
        raise ValueError(f"Load expansion produced {len(arr)} values; expected {HOURS_IN_YEAR}.")
    return arr


def _dispatch(
    load: Load,
    base_dir: pathlib.Path | None,
    peak_month: str,
) -> np.ndarray:
    src = load.source

    # ------------------------------------------------------------------
    # hourly_csv: 8 760-row single-column CSV [kW]
    # ------------------------------------------------------------------
    if src == "hourly_csv":
        if load.csv_path is None:
            raise ValueError("load.csv_path is required when load.source='hourly_csv'.")
        path = _resolve_csv_path(load.csv_path, base_dir)
        return _read_csv_1d(path, HOURS_IN_YEAR)

    # ------------------------------------------------------------------
    # daily_csv: 24-row hourly profile tiled across 365 days -> 8 760 h
    # ------------------------------------------------------------------
    if src == "daily_csv":
        if load.csv_path is None:
            raise ValueError("load.csv_path is required when load.source='daily_csv'.")
        path = _resolve_csv_path(load.csv_path, base_dir)
        daily = _read_csv_1d(path, 24)
        return np.tile(daily, 365)

    # ------------------------------------------------------------------
    # monthly_hourly_average: CSV with either
    #   (a) 12 rows (one monthly-average kW) -> expand month-by-month, or
    #   (b) 288 rows (12 months x 24 hours) -> expand month-by-month
    # ------------------------------------------------------------------
    if src == "monthly_hourly_average":
        if load.csv_path is None:
            raise ValueError("load.csv_path is required when load.source='monthly_hourly_average'.")
        path = _resolve_csv_path(load.csv_path, base_dir)
        data = _read_csv_1d(path, None)
        if data.shape[0] == 12:
            # Simple monthly-average scalar per month
            return _expand_monthly_averages(data)
        if data.shape[0] == 288:
            # 12 x 24 matrix stored row-major
            matrix = data.reshape(12, 24)
            result = np.empty(HOURS_IN_YEAR, dtype=np.float64)
            idx = 0
            for m, days in enumerate(DAYS_IN_MONTH):
                for _ in range(days):
                    result[idx : idx + 24] = matrix[m]
                    idx += 24
            return result
        raise ValueError(
            f"monthly_hourly_average CSV must have 12 or 288 rows; got {data.shape[0]}."
        )

    # ------------------------------------------------------------------
    # annual_daily_average: 24-row daily average profile -> tile 365 days
    # (same mechanics as daily_csv; semantics differ)
    # ------------------------------------------------------------------
    if src == "annual_daily_average":
        if load.csv_path is None:
            raise ValueError("load.csv_path is required when load.source='annual_daily_average'.")
        path = _resolve_csv_path(load.csv_path, base_dir)
        daily = _read_csv_1d(path, 24)
        return np.tile(daily, 365)

    # ------------------------------------------------------------------
    # annual_hourly_average: 8 760-row CSV (no scale_factor here -- handled
    # by the caller via load.scale_factor)
    # ------------------------------------------------------------------
    if src == "annual_hourly_average":
        if load.csv_path is None:
            raise ValueError("load.csv_path is required when load.source='annual_hourly_average'.")
        path = _resolve_csv_path(load.csv_path, base_dir)
        return _read_csv_1d(path, HOURS_IN_YEAR)

    # ------------------------------------------------------------------
    # monthly_total: 12 monthly kWh totals -> convert to average kW,
    # then expand via monthly-average method
    # ------------------------------------------------------------------
    if src == "monthly_total":
        if not load.monthly_peak:
            raise ValueError("monthly_total source requires monthly_peak (12 monthly kWh totals).")
        monthly_avg_kw = np.array(
            [
                kwh / (24.0 * days)
                for kwh, days in zip(load.monthly_peak, DAYS_IN_MONTH, strict=True)
            ]
        )
        return _expand_monthly_averages(monthly_avg_kw)

    # ------------------------------------------------------------------
    # generic_monthly: scale generic CSV shape to per-month kWh totals
    # (monthly_peak holds monthly kWh totals here)
    # ------------------------------------------------------------------
    if src == "generic_monthly":
        if not load.monthly_peak:
            raise ValueError(
                "generic_monthly source requires monthly_peak (12 monthly kWh totals)."
            )
        return build_generic_load_from_monthly(peak_month, load.monthly_peak)

    # ------------------------------------------------------------------
    # generic_annual_total: build generic profile scaled to annual_kwh total
    # ------------------------------------------------------------------
    if src == "generic_annual_total":
        if load.annual_kwh is None:
            raise ValueError("load.annual_kwh is required when load.source='generic_annual_total'")
        return build_generic_load_from_annual_total(peak_month, load.annual_kwh)

    # ------------------------------------------------------------------
    # generic_annual: normalized generic CSV shape; scale_factor scales it
    # ------------------------------------------------------------------
    if src == "generic_annual":
        return build_generic_load_normalized(peak_month)

    # ------------------------------------------------------------------
    # generic: identical to generic_annual for Phase 3
    # ------------------------------------------------------------------
    if src == "generic":
        return build_generic_load_normalized(peak_month)

    # ------------------------------------------------------------------
    # template (v4): built-in residential/commercial/industrial shape
    # scaled to annual_kwh.
    # ------------------------------------------------------------------
    if src == "template":
        from samba.load_profiles.templates import build_load_from_template

        if load.template_name is None:
            raise ValueError("load.template_name is required when load.source='template'")
        if load.annual_kwh is None:
            raise ValueError("load.annual_kwh is required when load.source='template'")
        return build_load_from_template(load.template_name, load.annual_kwh)

    raise NotImplementedError(f"Load source '{src}' is not yet implemented.")
