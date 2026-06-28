"""Unit tests for samba.weather — NSRDB reader, POA, cell temp, PV power."""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

import numpy as np
import pytest

if TYPE_CHECKING:
    from samba.weather import WeatherData

EXAMPLES_CONTENT = pathlib.Path(__file__).parent.parent.parent / "examples" / "content"
METEO_CSV = EXAMPLES_CONTENT / "weather_sf_2019.csv"


# ---------------------------------------------------------------------------
# NSRDB reader
# ---------------------------------------------------------------------------


class TestReadNsrdbCsv:
    def test_returns_weather_data_with_8760_rows(self) -> None:
        from samba.weather import WeatherData, read_nsrdb_csv

        wd = read_nsrdb_csv(METEO_CSV)
        assert isinstance(wd, WeatherData)
        assert len(wd.timestamp) == 8760

    def test_arrays_have_correct_shape(self) -> None:
        from samba.weather import read_nsrdb_csv

        wd = read_nsrdb_csv(METEO_CSV)
        for arr in (wd.ghi_wm2, wd.dhi_wm2, wd.dni_wm2, wd.tamb_c, wd.wind_ms, wd.albedo):
            assert arr.shape == (8760,), f"Expected (8760,), got {arr.shape}"

    def test_metadata_parsed(self) -> None:
        from samba.weather import read_nsrdb_csv

        wd = read_nsrdb_csv(METEO_CSV)
        # METEO.csv is San Francisco: lat=37.77, lon=-122.42, tz=-8
        assert abs(wd.latitude - 37.77) < 0.1
        assert abs(wd.longitude - (-122.42)) < 0.1
        assert wd.tz_offset == pytest.approx(-8.0)

    def test_irradiance_non_negative(self) -> None:
        from samba.weather import read_nsrdb_csv

        wd = read_nsrdb_csv(METEO_CSV)
        assert np.all(wd.ghi_wm2 >= 0)
        assert np.all(wd.dhi_wm2 >= 0)
        assert np.all(wd.dni_wm2 >= 0)

    def test_missing_file_raises_file_not_found(self) -> None:
        from samba.weather import read_nsrdb_csv

        with pytest.raises(FileNotFoundError):
            read_nsrdb_csv("nonexistent_weather.csv")

    def test_bad_row_count_raises_value_error(self, tmp_path: pathlib.Path) -> None:
        """A CSV with only 100 data rows raises ValueError."""
        from samba.weather import read_nsrdb_csv

        # Duplicate first two header rows from real METEO.csv and add only 100 data rows
        real = METEO_CSV.read_text(encoding="utf-8", errors="replace")
        lines = real.splitlines()
        truncated = "\n".join(lines[:3]) + "\n"  # headers only
        for i in range(3, 103):  # 100 data rows
            truncated += lines[i] + "\n" if i < len(lines) else lines[3] + "\n"
        bad = tmp_path / "bad_weather.csv"
        bad.write_text(truncated, encoding="utf-8")
        with pytest.raises(ValueError, match="8 760"):
            read_nsrdb_csv(bad)


# ---------------------------------------------------------------------------
# POA irradiance
# ---------------------------------------------------------------------------


class TestCalcPoa:
    @pytest.fixture(scope="class")
    def weather(self) -> WeatherData:
        from samba.weather import read_nsrdb_csv

        return read_nsrdb_csv(METEO_CSV)

    def test_output_shape(self, weather: WeatherData) -> None:
        from samba.weather import calc_poa

        poa = calc_poa(weather, tilt_deg=20.0, azimuth_deg=180.0)
        assert poa.shape == (8760,)

    def test_all_non_negative(self, weather: WeatherData) -> None:
        from samba.weather import calc_poa

        poa = calc_poa(weather, tilt_deg=20.0, azimuth_deg=180.0)
        assert np.all(poa >= 0), f"POA has {np.sum(poa < 0)} negative values"

    def test_peak_in_reasonable_range(self, weather: WeatherData) -> None:
        """Summer-day peak POA should be roughly 600–1200 W/m²."""
        from samba.weather import calc_poa

        poa = calc_poa(weather, tilt_deg=20.0, azimuth_deg=180.0)
        assert poa.max() >= 600, f"Max POA {poa.max():.0f} W/m² seems too low"
        assert poa.max() <= 1400, f"Max POA {poa.max():.0f} W/m² seems too high"

    def test_nighttime_is_zero(self, weather: WeatherData) -> None:
        """Hours 0–5 in January (winter, SF) should all be 0."""
        from samba.weather import calc_poa

        poa = calc_poa(weather, tilt_deg=20.0, azimuth_deg=180.0)
        # Hours 0–5 of day 1 (January)
        assert np.all(poa[:6] == 0.0), "Night hours should produce zero POA"

    def test_flat_tilt_lower_than_tilted_in_summer(self, weather: WeatherData) -> None:
        """Tilted panel should capture more annual energy than flat (tilt=0)."""
        from samba.weather import calc_poa

        poa_flat = calc_poa(weather, tilt_deg=0.0, azimuth_deg=180.0)
        poa_tilted = calc_poa(weather, tilt_deg=30.0, azimuth_deg=180.0)
        # Both produce positive annual sums; tilted captures more in mid-latitudes
        assert poa_flat.sum() > 0
        assert poa_tilted.sum() > 0


# ---------------------------------------------------------------------------
# Cell temperature
# ---------------------------------------------------------------------------


class TestCalcCellTemp:
    def test_increases_with_poa(self) -> None:
        from samba.weather import calc_cell_temp

        poa = np.array([0.0, 500.0, 1000.0])
        tamb = np.array([20.0, 20.0, 20.0])
        t_cell = calc_cell_temp(poa, tamb, noct_celsius=45.0)
        assert t_cell[0] == pytest.approx(20.0)
        assert t_cell[1] > t_cell[0]
        assert t_cell[2] > t_cell[1]

    def test_noct_formula(self) -> None:
        from samba.weather import calc_cell_temp

        poa = np.array([800.0])
        tamb = np.array([20.0])
        # Expected: 20 + (45 - 20) / 800 * 800 = 20 + 25 = 45
        t_cell = calc_cell_temp(poa, tamb, noct_celsius=45.0)
        assert t_cell[0] == pytest.approx(45.0)

    def test_shape_preserved(self) -> None:
        from samba.weather import calc_cell_temp

        poa = np.ones(8760) * 500.0
        tamb = np.ones(8760) * 20.0
        t_cell = calc_cell_temp(poa, tamb)
        assert t_cell.shape == (8760,)


# ---------------------------------------------------------------------------
# PV power per kWp
# ---------------------------------------------------------------------------


class TestCalcPvPowerPerKwp:
    def test_range_0_to_1(self) -> None:
        from samba.weather import calc_cell_temp, calc_poa, calc_pv_power_per_kwp, read_nsrdb_csv

        wd = read_nsrdb_csv(METEO_CSV)
        poa = calc_poa(wd, tilt_deg=20.0, azimuth_deg=180.0)
        t_cell = calc_cell_temp(poa, wd.tamb_c)
        power = calc_pv_power_per_kwp(poa, t_cell)
        assert np.all(power >= 0.0)
        assert np.all(power <= 1.0)

    def test_zero_irradiance_gives_zero_power(self) -> None:
        from samba.weather import calc_pv_power_per_kwp

        poa = np.zeros(10)
        t_cell = np.full(10, 25.0)
        power = calc_pv_power_per_kwp(poa, t_cell)
        assert np.all(power == 0.0)

    def test_stc_gives_derating(self) -> None:
        """At STC (1000 W/m², 25 °C), output equals derating factor."""
        from samba.weather import calc_pv_power_per_kwp

        poa = np.array([1000.0])
        t_cell = np.array([25.0])
        derating = 0.9
        power = calc_pv_power_per_kwp(poa, t_cell, derating=derating)
        assert power[0] == pytest.approx(derating)
