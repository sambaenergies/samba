"""Integration tests for Phase 3 data pipeline: weather → POA → load → tariff."""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

EXAMPLES_CONTENT = pathlib.Path(__file__).parent.parent.parent / "examples" / "content"
METEO_CSV = EXAMPLES_CONTENT / "weather_sf_2019.csv"
ELOAD_CSV = EXAMPLES_CONTENT / "load_residential_8760.csv"


@pytest.mark.integration
class TestWeatherToPoa:
    """Read real NSRDB file → compute POA → sanity checks."""

    def test_full_weather_to_poa_pipeline(self) -> None:
        from samba.weather import calc_poa, read_nsrdb_csv

        wd = read_nsrdb_csv(METEO_CSV)
        poa = calc_poa(wd, tilt_deg=20.0, azimuth_deg=180.0)
        assert poa.shape == (8760,)
        assert np.all(poa >= 0.0)
        # Annual irradiation should be between 1000 and 2500 kWh/m²
        annual_kwh = poa.sum() / 1000.0
        assert 1000.0 <= annual_kwh <= 2500.0, f"Unexpected annual irradiation {annual_kwh:.0f}"

    def test_pv_power_pipeline(self) -> None:
        from samba.weather import (
            calc_cell_temp,
            calc_poa,
            calc_pv_power_per_kwp,
            read_nsrdb_csv,
        )

        wd = read_nsrdb_csv(METEO_CSV)
        poa = calc_poa(wd, tilt_deg=20.0, azimuth_deg=180.0)
        t_cell = calc_cell_temp(poa, wd.tamb_c, noct_celsius=45.0)
        power = calc_pv_power_per_kwp(poa, t_cell, derating=0.9)

        assert power.shape == (8760,)
        assert np.all(power >= 0.0)
        assert np.all(power <= 1.0)

        # Annual specific yield for SF location and 20° tilt should be > 1000 h
        annual_h = float(power.sum())
        assert annual_h > 1000.0, f"Low annual yield: {annual_h:.0f} h"


@pytest.mark.integration
class TestLoadPipeline:
    """Read CSV load file → expand → sanity checks."""

    def test_load_csv_to_array(self) -> None:
        from samba.load_profiles import expand_load
        from samba.scenario.models import Load

        load = Load(source="hourly_csv", csv_path=str(ELOAD_CSV))
        arr = expand_load(load, base_dir=EXAMPLES_CONTENT)
        assert arr.shape == (8760,)
        assert np.all(arr >= 0.0)

    def test_annual_energy_positive_and_finite(self) -> None:
        from samba.load_profiles import expand_load
        from samba.scenario.models import Load

        load = Load(source="hourly_csv", csv_path=str(ELOAD_CSV))
        arr = expand_load(load, base_dir=EXAMPLES_CONTENT)
        annual_kwh = float(arr.sum())
        assert np.isfinite(annual_kwh)
        assert annual_kwh > 0.0


@pytest.mark.integration
class TestTariffPipeline:
    """Build tariff arrays from real scenario configurations."""

    def test_flat_tariff_pipeline(self) -> None:
        from samba.scenario.models import BuyRate, Tariff
        from samba.tariff import TariffArrays, resolve_tariff

        tariff = Tariff(buy=BuyRate(type="flat", rate_per_kwh=0.14))
        load_kw = np.ones(8760) * 3.0
        arrays = resolve_tariff(tariff, load_kw=load_kw)

        assert isinstance(arrays, TariffArrays)
        assert arrays.cbuy.shape == (8760,)
        assert arrays.csell.shape == (8760,)
        assert arrays.service_charge.shape == (12,)
        assert np.all(arrays.cbuy == pytest.approx(0.14))
        assert np.all(arrays.csell == 0.0)
        assert np.all(arrays.service_charge == 0.0)

    def test_tou_tariff_with_sell_and_service_charge(self) -> None:
        from samba.scenario.models import BuyRate, SellRate, ServiceCharge, Tariff, TouPeriod
        from samba.tariff import resolve_tariff

        all_months = list(range(1, 13))

        tou = [
            TouPeriod(
                name="off_peak",
                months=all_months,
                weekday=True,
                weekend=True,
                hours=list(range(0, 16)) + list(range(21, 24)),
                rate_per_kwh=0.08,
            ),
            TouPeriod(
                name="peak",
                months=all_months,
                weekday=True,
                weekend=True,
                hours=list(range(16, 21)),
                rate_per_kwh=0.25,
            ),
        ]
        tariff = Tariff(
            buy=BuyRate(type="tou", tou_schedule=tou),
            sell=SellRate(type="flat", rate_per_kwh=0.04),
            service_charge=ServiceCharge(type="flat", monthly_flat=8.50),
        )
        from samba.load_profiles import expand_load
        from samba.scenario.models import Load

        load = Load(source="hourly_csv", csv_path=str(ELOAD_CSV))
        load_kw = expand_load(load, base_dir=EXAMPLES_CONTENT)

        arrays = resolve_tariff(tariff, load_kw=load_kw)
        assert arrays.cbuy.max() == pytest.approx(0.25)
        assert np.all(arrays.csell == pytest.approx(0.04))
        assert np.all(arrays.service_charge == pytest.approx(8.50))


@pytest.mark.integration
class TestEndToEndDataPipeline:
    """Weather + load + tariff pipeline together."""

    def test_annual_electricity_cost_positive(self) -> None:
        """Annual cost = sum(load × cbuy) should be positive and finite."""
        from samba.load_profiles import expand_load
        from samba.scenario.models import BuyRate, Load, Tariff
        from samba.tariff import resolve_tariff

        load = Load(source="hourly_csv", csv_path=str(ELOAD_CSV))
        load_kw = expand_load(load, base_dir=EXAMPLES_CONTENT)

        tariff = Tariff(buy=BuyRate(type="flat", rate_per_kwh=0.14))
        arrays = resolve_tariff(tariff, load_kw=load_kw)

        annual_cost = float((load_kw * arrays.cbuy).sum())
        assert np.isfinite(annual_cost)
        assert annual_cost > 0.0
