# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Typed container for an 8760-hour weather dataset."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class WeatherData:
    """Hourly weather for one non-leap year (8 760 rows).

    All irradiance arrays are in **W/m2**.  Temperature is in **degC**.
    Wind speed is in **m/s**.
    """

    timestamp: pd.DatetimeIndex  # 8 760 UTC-aware or naive hourly timestamps
    ghi_wm2: np.ndarray  # Global Horizontal Irradiance
    dhi_wm2: np.ndarray  # Diffuse Horizontal Irradiance
    dni_wm2: np.ndarray  # Direct Normal Irradiance
    tamb_c: np.ndarray  # Ambient temperature [degC]
    wind_ms: np.ndarray  # Wind speed [m/s]
    albedo: np.ndarray  # Surface albedo [0-1]; defaults to 0.2 if not provided
    latitude: float  # [degN]
    longitude: float  # [degE]
    tz_offset: float  # Hours from UTC (e.g. -8 for US/Pacific standard)

    def __post_init__(self) -> None:
        expected = 8760
        arrays = {
            "ghi_wm2": self.ghi_wm2,
            "dhi_wm2": self.dhi_wm2,
            "dni_wm2": self.dni_wm2,
            "tamb_c": self.tamb_c,
            "wind_ms": self.wind_ms,
            "albedo": self.albedo,
        }
        for name, arr in arrays.items():
            if arr.shape != (expected,):
                raise ValueError(
                    f"WeatherData.{name} must have shape ({expected},); got {arr.shape}"
                )
        if len(self.timestamp) != expected:
            raise ValueError(
                f"WeatherData.timestamp must have {expected} entries; got {len(self.timestamp)}"
            )


def stub_weather(
    latitude: float = 37.77,
    longitude: float = -122.42,
    tz_offset: float = -8.0,
) -> WeatherData:
    """Return a zero-filled 8760-hour :class:'WeatherData' suitable for testing.

    All irradiance / wind arrays are zero; ambient temperature is 20 degC; albedo
    is 0.2.  Timestamps are UTC-based starting 2023-01-01.

    Parameters
    ----------
    latitude, longitude:
        Metadata stored on the stub (does not affect array values).
    tz_offset:
        UTC offset in hours.

    Returns
    -------
    WeatherData
        A valid 8760-row WeatherData with zero-energy inputs.
    """
    n = 8760
    ts = pd.date_range("2023-01-01", periods=n, freq="h", tz="UTC")
    zeros: np.ndarray = np.zeros(n, dtype=np.float64)
    return WeatherData(
        timestamp=ts,
        ghi_wm2=zeros.copy(),
        dhi_wm2=zeros.copy(),
        dni_wm2=zeros.copy(),
        tamb_c=np.full(n, 20.0, dtype=np.float64),
        wind_ms=zeros.copy(),
        albedo=np.full(n, 0.2, dtype=np.float64),
        latitude=latitude,
        longitude=longitude,
        tz_offset=tz_offset,
    )
