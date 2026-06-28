# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""NSRDB (National Solar Radiation Database) CSV file reader.

The NSRDB download format has three header rows:
  Row 1: site metadata (Latitude, Longitude, Time Zone, Elevation, ...)
  Row 2: units header
  Row 3: column names
  Rows 4+: 8 760 (or 8 784 for leap years) hourly data records

This reader rejects leap-year files: SAMBA v1 operates on 8 760-hour years.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

from samba.weather.models import WeatherData


def read_nsrdb_csv(path: str | pathlib.Path) -> WeatherData:
    """Parse an NSRDB CSV file and return a :class:'WeatherData' instance.

    Parameters
    ----------
    path:
        File system path to the NSRDB ''.csv'' file.

    Returns
    -------
    WeatherData
        An 8 760-row weather dataset.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file does not have exactly 8 760 data rows or the required
        columns are missing.
    """
    path = pathlib.Path(path)
    if not path.exists():
        raise FileNotFoundError(f"NSRDB CSV not found: {path}")

    # --- Row 1: site metadata ---
    meta_df = pd.read_csv(path, nrows=1, header=0)
    try:
        latitude = float(meta_df["Latitude"].iloc[0])
        longitude = float(meta_df["Longitude"].iloc[0])
        tz_offset = float(meta_df["Time Zone"].iloc[0])
    except KeyError as exc:
        raise ValueError(f"NSRDB metadata row is missing expected column: {exc}") from exc

    # --- Rows 3+: data (skip first two header rows) ---
    df = pd.read_csv(path, skiprows=2)

    required_cols = {
        "Year",
        "Month",
        "Day",
        "Hour",
        "GHI",
        "DHI",
        "DNI",
        "Temperature",
        "Wind Speed",
    }
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"NSRDB CSV is missing columns: {sorted(missing)}")

    # Drop leap-day rows (February 29) to enforce non-leap-year requirement.
    leap_mask = (df["Month"] == 2) & (df["Day"] == 29)
    if leap_mask.any():
        df = df[~leap_mask].reset_index(drop=True)

    n_rows = len(df)
    if n_rows != 8760:
        raise ValueError(
            f"NSRDB CSV must contain exactly 8 760 data rows; got {n_rows}. "
            "Ensure the file covers a non-leap year."
        )

    # Build a DatetimeIndex from Year/Month/Day/Hour columns.
    timestamp = pd.to_datetime(df[["Year", "Month", "Day", "Hour"]])

    # Extract irradiance and met columns as numpy float arrays.
    ghi = df["GHI"].to_numpy(dtype=np.float64)
    dhi = df["DHI"].to_numpy(dtype=np.float64)
    dni = df["DNI"].to_numpy(dtype=np.float64)
    tamb = df["Temperature"].to_numpy(dtype=np.float64)
    wind = df["Wind Speed"].to_numpy(dtype=np.float64)

    # Surface albedo is optional; default to 0.2 (grass/typical).
    if "Surface Albedo" in df.columns:
        albedo = df["Surface Albedo"].to_numpy(dtype=np.float64)
    else:
        albedo = np.full(8760, 0.2)

    return WeatherData(
        timestamp=pd.DatetimeIndex(timestamp),
        ghi_wm2=ghi,
        dhi_wm2=dhi,
        dni_wm2=dni,
        tamb_c=tamb,
        wind_ms=wind,
        albedo=albedo,
        latitude=latitude,
        longitude=longitude,
        tz_offset=tz_offset,
    )
