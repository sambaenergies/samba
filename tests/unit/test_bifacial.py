# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for the v4 bifacial PV rear-side gain in calc_poa."""

from __future__ import annotations

import numpy as np
import pandas as pd

from samba.weather.models import WeatherData
from samba.weather.poa import calc_poa


def _sunny_weather(albedo: float = 0.2) -> WeatherData:
    """A simple clear-sky-ish year: midday GHI/DNI bell, others derived."""
    ts = pd.date_range("2023-01-01", periods=8760, freq="h")
    hod = np.arange(8760) % 24
    bell = np.clip(np.sin((hod - 6) / 12.0 * np.pi), 0.0, 1.0)
    ghi = 900.0 * bell
    dni = 800.0 * bell
    dhi = 100.0 * bell
    return WeatherData(
        timestamp=ts,
        ghi_wm2=ghi,
        dhi_wm2=dhi,
        dni_wm2=dni,
        tamb_c=np.full(8760, 20.0),
        wind_ms=np.full(8760, 2.0),
        albedo=np.full(8760, albedo),
        latitude=37.0,
        longitude=-122.0,
        tz_offset=-8.0,
    )


class TestBifacialPOA:
    def test_monofacial_unchanged_by_bifaciality(self) -> None:
        w = _sunny_weather()
        base = calc_poa(w, tilt_deg=30.0, azimuth_deg=180.0)
        # monofacial ignores bifaciality entirely
        same = calc_poa(
            w, tilt_deg=30.0, azimuth_deg=180.0, module_type="monofacial", bifaciality=0.9
        )
        np.testing.assert_allclose(base, same)

    def test_bifacial_adds_rear_gain(self) -> None:
        w = _sunny_weather()
        mono = calc_poa(w, tilt_deg=30.0, azimuth_deg=180.0, module_type="monofacial")
        bif = calc_poa(w, tilt_deg=30.0, azimuth_deg=180.0, module_type="bifacial", bifaciality=0.8)
        assert bif.sum() > mono.sum()  # rear gain raises annual POA
        assert np.all(bif >= mono - 1e-9)  # never below the front-only value

    def test_zero_bifaciality_no_gain(self) -> None:
        w = _sunny_weather()
        mono = calc_poa(w, tilt_deg=30.0, azimuth_deg=180.0, module_type="monofacial")
        bif0 = calc_poa(
            w, tilt_deg=30.0, azimuth_deg=180.0, module_type="bifacial", bifaciality=0.0
        )
        np.testing.assert_allclose(mono, bif0)

    def test_rear_gain_scales_with_albedo(self) -> None:
        low = _sunny_weather(albedo=0.1)
        high = _sunny_weather(albedo=0.5)
        bif_low = calc_poa(
            low, tilt_deg=30.0, azimuth_deg=180.0, module_type="bifacial", bifaciality=0.8
        )
        bif_high = calc_poa(
            high, tilt_deg=30.0, azimuth_deg=180.0, module_type="bifacial", bifaciality=0.8
        )
        assert bif_high.sum() > bif_low.sum()  # more ground reflectance -> more rear gain
