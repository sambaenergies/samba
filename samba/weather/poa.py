# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Plane-of-array irradiance and PV output calculations.

Solar position and plane-of-array transposition are delegated to
`pvlib <https://pvlib-python.readthedocs.io>`_ (BSD-3): NREL SPA solar position
and an isotropic (Liu & Jordan) sky-diffuse transposition. The cell-temperature
(NOCT) and per-kWp power models below are SAMBA's own.

References
----------
- pvlib: Holmgren, Hansen & Mikofski, *J. Open Source Software* 3(29), 884 (2018).
- Liu & Jordan, "The interrelationship and characteristic distribution of
  direct, diffuse and total solar radiation", *Solar Energy* 4(3), 1960.
- Duffie & Beckman, *Solar Engineering of Thermal Processes*, 4th ed.
"""

from __future__ import annotations

from datetime import timedelta, timezone

import numpy as np
import pandas as pd
import pvlib

from samba.weather.models import WeatherData


def calc_poa(
    weather: WeatherData,
    tilt_deg: float,
    azimuth_deg: float,
    module_type: str = "monofacial",
    bifaciality: float = 0.0,
) -> np.ndarray:
    """Compute plane-of-array (POA) irradiance for each hour of the year.

    Uses pvlib for solar position and an isotropic-sky transposition.

    Parameters
    ----------
    weather:
        Parsed site weather dataset with 8 760 rows.
    tilt_deg:
        Panel tilt from horizontal [deg].  0 = flat, 90 = vertical.
    azimuth_deg:
        Panel azimuth measured clockwise from North [deg] (pvlib convention;
        180 = south-facing).
    module_type:
        ``"monofacial"`` (default) or ``"bifacial"``.
    bifaciality:
        Rear/front efficiency ratio (0-1); only used when
        ``module_type == "bifacial"``.

    Returns
    -------
    np.ndarray, shape (8760,)
        Effective POA irradiance in W/m2, all values >= 0.  For a bifacial
        module this is the front POA plus ``bifaciality x`` an estimated rear
        ground-reflected irradiance.
    """
    times = pd.DatetimeIndex(weather.timestamp)
    if times.tz is None:
        times = times.tz_localize(timezone(timedelta(hours=float(weather.tz_offset))))

    solpos = pvlib.solarposition.get_solarposition(times, weather.latitude, weather.longitude)

    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=float(tilt_deg),
        surface_azimuth=float(azimuth_deg),
        solar_zenith=solpos["apparent_zenith"].to_numpy(),
        solar_azimuth=solpos["azimuth"].to_numpy(),
        dni=np.asarray(weather.dni_wm2, dtype=np.float64),
        ghi=np.asarray(weather.ghi_wm2, dtype=np.float64),
        dhi=np.asarray(weather.dhi_wm2, dtype=np.float64),
        albedo=np.asarray(weather.albedo, dtype=np.float64),
        model="isotropic",
    )
    poa_front = np.nan_to_num(np.asarray(poa["poa_global"], dtype=np.float64), nan=0.0)

    # Rear-side (bifacial) gain: the panel back faces the ground with the
    # complementary view factor (1 + cos(tilt))/2, collecting mostly
    # ground-reflected irradiance, scaled by the module's bifaciality.
    if module_type == "bifacial" and bifaciality > 0.0:
        rear_poa = weather.albedo * weather.ghi_wm2 * (1.0 + np.cos(np.deg2rad(tilt_deg))) / 2.0
        poa_front = poa_front + bifaciality * rear_poa

    return np.asarray(np.maximum(poa_front, 0.0), dtype=np.float64)


def calc_cell_temp(
    poa: np.ndarray,
    tamb_c: np.ndarray,
    noct_celsius: float = 45.0,
) -> np.ndarray:
    """Estimate PV cell temperature using the NOCT model.

    .. math::
        T_{\\text{cell}} = T_{\\text{amb}} + \\frac{NOCT - 20}{800} \\cdot POA

    Parameters
    ----------
    poa:
        Plane-of-array irradiance [W/m2], shape (8760,).
    tamb_c:
        Ambient temperature [degC], shape (8760,).
    noct_celsius:
        Nominal Operating Cell Temperature [degC].  Typically 43-47 degC.

    Returns
    -------
    np.ndarray, shape (8760,)
        Cell temperature [degC].
    """
    return tamb_c + ((noct_celsius - 20.0) / 800.0) * poa


def calc_pv_power_per_kwp(
    poa: np.ndarray,
    t_cell: np.ndarray,
    temp_coeff: float = -0.004,
    derating: float = 0.9,
) -> np.ndarray:
    """Compute normalised PV output per kW_p of installed capacity.

    .. math::
        P = \\frac{POA}{1000} \\cdot (1 + \\gamma \\cdot (T_{\\text{cell}} - 25))
            \\cdot \\delta

    where :math:'\\gamma' = ''temp_coeff'' and :math:'\\delta' = ''derating''.

    Parameters
    ----------
    poa:
        Plane-of-array irradiance [W/m2], shape (8760,).
    t_cell:
        Cell temperature [degC], shape (8760,).
    temp_coeff:
        Temperature coefficient of maximum power [1/degC].  Typically -0.004.
    derating:
        Overall DC derating factor (soiling, mismatch, wiring, ...).  (0, 1].

    Returns
    -------
    np.ndarray, shape (8760,)
        Per-unit power output [kWh per kW_p], clipped to [0, 1].
    """
    power = (poa / 1000.0) * (1.0 + temp_coeff * (t_cell - 25.0)) * derating
    return np.clip(power, 0.0, 1.0)
