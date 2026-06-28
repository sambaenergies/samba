"""Unit tests for samba.tariff — all rate calculators and the resolver."""

from __future__ import annotations

import numpy as np
import pytest

from samba.scenario.models import (
    BuyRate,
    SeasonalRate,
    SeasonalTiers,
    SellRate,
    ServiceCharge,
    Tariff,
    TierLevel,
    TouPeriod,
)

# ---------------------------------------------------------------------------
# Helpers — full-year TOU schedule (all 24 hours × 12 months × both day types)
# ---------------------------------------------------------------------------

_ALL_MONTHS = list(range(1, 13))
_ALL_HOURS = list(range(0, 24))

_FLAT_PERIOD = TouPeriod(
    name="flat",
    months=_ALL_MONTHS,
    weekday=True,
    weekend=True,
    hours=_ALL_HOURS,
    rate_per_kwh=0.10,
)

_PEAK_PERIOD = TouPeriod(
    name="peak",
    months=list(range(6, 10)),
    weekday=True,
    weekend=False,
    hours=list(range(16, 21)),
    rate_per_kwh=0.30,
)

_OFF_PEAK_PERIOD = TouPeriod(
    name="off_peak",
    months=list(range(6, 10)),
    weekday=True,
    weekend=False,
    hours=[h for h in _ALL_HOURS if h not in range(16, 21)],
    rate_per_kwh=0.08,
)

_SAMPLE_LOAD_KW = np.ones(8760, dtype=np.float64) * 2.0


# ---------------------------------------------------------------------------
# calc_flat_rate
# ---------------------------------------------------------------------------


class TestCalcFlatRate:
    def test_all_equal_to_rate(self) -> None:
        from samba.tariff.flat import calc_flat_rate

        arr = calc_flat_rate(0.12)
        assert arr.shape == (8760,)
        assert np.all(arr == pytest.approx(0.12))

    def test_zero_rate(self) -> None:
        from samba.tariff.flat import calc_flat_rate

        arr = calc_flat_rate(0.0)
        assert np.all(arr == 0.0)


# ---------------------------------------------------------------------------
# calc_tou_rate
# ---------------------------------------------------------------------------


class TestCalcTouRate:
    def test_shape(self) -> None:
        from samba.tariff.tou import calc_tou_rate

        arr = calc_tou_rate([_FLAT_PERIOD])
        assert arr.shape == (8760,)

    def test_flat_all_same(self) -> None:
        from samba.tariff.tou import calc_tou_rate

        arr = calc_tou_rate([_FLAT_PERIOD])
        assert np.all(arr == pytest.approx(0.10))

    def test_peak_hours_have_higher_rate(self) -> None:
        from samba.tariff.tou import calc_tou_rate

        arr = calc_tou_rate([_FLAT_PERIOD, _PEAK_PERIOD])
        # Peak rate 0.30 should appear somewhere in summer (months 6-9), hour 16-20, weekday
        assert arr.max() == pytest.approx(0.30)
        assert arr.min() == pytest.approx(0.10)

    def test_later_period_overrides_earlier(self) -> None:
        """If two periods overlap, the later-listed one wins."""
        from samba.tariff.tou import calc_tou_rate

        p1 = TouPeriod(
            name="base",
            months=_ALL_MONTHS,
            weekday=True,
            weekend=True,
            hours=_ALL_HOURS,
            rate_per_kwh=0.10,
        )
        p2 = TouPeriod(
            name="override",
            months=_ALL_MONTHS,
            weekday=True,
            weekend=True,
            hours=[12],
            rate_per_kwh=0.20,
        )
        arr = calc_tou_rate([p1, p2])
        # Hour 12 each day should be 0.20
        assert arr[12] == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# calc_tiered_rate
# ---------------------------------------------------------------------------


class TestCalcTieredRate:
    def test_shape(self) -> None:
        from samba.tariff.tiered import calc_tiered_rate

        tiers = [
            TierLevel(limit_kwh=500.0, rate_per_kwh=0.10),
            TierLevel(limit_kwh=None, rate_per_kwh=0.15),
        ]
        arr = calc_tiered_rate(tiers, _SAMPLE_LOAD_KW)
        assert arr.shape == (8760,)

    def test_low_usage_first_tier(self) -> None:
        """Very low monthly usage stays in first tier for entire year."""
        from samba.tariff.tiered import calc_tiered_rate

        tiers = [
            TierLevel(limit_kwh=10_000.0, rate_per_kwh=0.10),
            TierLevel(limit_kwh=None, rate_per_kwh=0.20),
        ]
        # 0.001 kW × 8760 h = 8.76 kWh/year → always first tier
        arr = calc_tiered_rate(tiers, np.full(8760, 0.001))
        assert np.all(arr == pytest.approx(0.10))

    def test_high_usage_crosses_tier(self) -> None:
        """Very high usage must produce some hours at second-tier rate."""
        from samba.tariff.tiered import calc_tiered_rate

        tiers = [
            TierLevel(limit_kwh=100.0, rate_per_kwh=0.10),
            TierLevel(limit_kwh=None, rate_per_kwh=0.25),
        ]
        arr = calc_tiered_rate(tiers, np.full(8760, 10.0))
        # At 10 kW, 100 kWh limit is hit in ~10 hours per month
        assert np.any(np.isclose(arr, 0.25))


# ---------------------------------------------------------------------------
# calc_seasonal_rate
# ---------------------------------------------------------------------------


class TestCalcSeasonalRate:
    def test_shape(self) -> None:
        from samba.tariff.seasonal import calc_seasonal_rate

        schedule = [
            SeasonalRate(name="winter", months=[1, 2, 3, 10, 11, 12], rate_per_kwh=0.08),
            SeasonalRate(name="summer", months=[4, 5, 6, 7, 8, 9], rate_per_kwh=0.14),
        ]
        arr = calc_seasonal_rate(schedule)
        assert arr.shape == (8760,)

    def test_correct_rates_per_season(self) -> None:
        from samba.tariff.seasonal import calc_seasonal_rate

        schedule = [
            SeasonalRate(name="winter", months=[1, 2, 3, 10, 11, 12], rate_per_kwh=0.08),
            SeasonalRate(name="summer", months=[4, 5, 6, 7, 8, 9], rate_per_kwh=0.14),
        ]
        arr = calc_seasonal_rate(schedule)
        # January is hours 0..743 → all should be 0.08
        assert np.all(arr[:744] == pytest.approx(0.08))
        # July is month 7 → somewhere in the array should be 0.14
        assert np.any(np.isclose(arr, 0.14))


# ---------------------------------------------------------------------------
# calc_seasonal_tiered_rate
# ---------------------------------------------------------------------------


class TestCalcSeasonalTieredRate:
    def test_shape(self) -> None:
        from samba.tariff.seasonal_tiered import calc_seasonal_tiered_rate

        seasonal_tiers = [
            SeasonalTiers(
                name="all_year",
                months=_ALL_MONTHS,
                tiers=[
                    TierLevel(limit_kwh=500.0, rate_per_kwh=0.10),
                    TierLevel(limit_kwh=None, rate_per_kwh=0.18),
                ],
            )
        ]
        arr = calc_seasonal_tiered_rate(seasonal_tiers, _SAMPLE_LOAD_KW)
        assert arr.shape == (8760,)


# ---------------------------------------------------------------------------
# calc_monthly_rate
# ---------------------------------------------------------------------------


class TestCalcMonthlyRate:
    def test_shape(self) -> None:
        from samba.tariff.monthly import calc_monthly_rate

        rates = [0.10, 0.10, 0.10, 0.12, 0.12, 0.14, 0.14, 0.14, 0.12, 0.10, 0.10, 0.10]
        arr = calc_monthly_rate(rates)
        assert arr.shape == (8760,)

    def test_january_rate_correct(self) -> None:
        from samba.tariff.monthly import calc_monthly_rate

        rates = [0.10] + [0.20] * 11
        arr = calc_monthly_rate(rates)
        assert arr[0] == pytest.approx(0.10)  # first hour of January
        assert arr[743] == pytest.approx(0.10)  # last hour of January


# ---------------------------------------------------------------------------
# calc_monthly_tiered_rate
# ---------------------------------------------------------------------------


class TestCalcMonthlyTieredRate:
    def test_shape(self) -> None:
        from samba.tariff.monthly_tiered import calc_monthly_tiered_rate

        month_tiers = [
            [
                TierLevel(limit_kwh=500.0, rate_per_kwh=0.10),
                TierLevel(limit_kwh=None, rate_per_kwh=0.18),
            ]
        ] * 12
        arr = calc_monthly_tiered_rate(month_tiers, _SAMPLE_LOAD_KW)
        assert arr.shape == (8760,)


# ---------------------------------------------------------------------------
# calc_ultra_low_tou_rate
# ---------------------------------------------------------------------------


class TestCalcUltraLowTouRate:
    def test_full_year_coverage_succeeds(self) -> None:
        from samba.tariff.ultra_low_tou import calc_ultra_low_tou_rate

        arr = calc_ultra_low_tou_rate([_FLAT_PERIOD])
        assert arr.shape == (8760,)
        assert not np.any(np.isnan(arr))

    def test_partial_coverage_raises_value_error(self) -> None:
        """Covering only hours 0-22 leaves hour 23 unassigned → ValueError."""
        from samba.tariff.ultra_low_tou import calc_ultra_low_tou_rate

        partial = TouPeriod(
            name="partial",
            months=_ALL_MONTHS,
            weekday=True,
            weekend=True,
            hours=list(range(0, 23)),  # hour 23 missing
            rate_per_kwh=0.10,
        )
        with pytest.raises(ValueError, match="unassigned"):
            calc_ultra_low_tou_rate([partial])

    def test_all_values_in_expected_range(self) -> None:
        from samba.tariff.ultra_low_tou import calc_ultra_low_tou_rate

        arr = calc_ultra_low_tou_rate([_FLAT_PERIOD])
        assert np.all(arr == pytest.approx(0.10))


# ---------------------------------------------------------------------------
# calc_service_charge
# ---------------------------------------------------------------------------


class TestCalcServiceCharge:
    def test_flat_shape_and_value(self) -> None:
        from samba.tariff.service_charge import calc_service_charge

        sc = ServiceCharge(type="flat", monthly_flat=15.0)
        arr = calc_service_charge(sc)
        assert arr.shape == (12,)
        assert np.all(arr == pytest.approx(15.0))

    def test_tiered_kwh_shape(self) -> None:
        from samba.tariff.service_charge import calc_service_charge

        sc = ServiceCharge(
            type="tiered_kwh",
            tiers=[
                TierLevel(limit_kwh=500.0, rate_per_kwh=8.0),
                TierLevel(limit_kwh=None, rate_per_kwh=12.0),
            ],
        )
        arr = calc_service_charge(sc, load_kw=_SAMPLE_LOAD_KW)
        assert arr.shape == (12,)
        assert np.all(arr > 0)


# ---------------------------------------------------------------------------
# resolve_tariff
# ---------------------------------------------------------------------------


class TestResolveTariff:
    def _flat_tariff(self) -> Tariff:
        return Tariff(buy=BuyRate(type="flat", rate_per_kwh=0.12))

    def test_shapes_correct(self) -> None:
        from samba.tariff import resolve_tariff

        arrays = resolve_tariff(self._flat_tariff(), load_kw=_SAMPLE_LOAD_KW)
        assert arrays.cbuy.shape == (8760,)
        assert arrays.csell.shape == (8760,)
        assert arrays.service_charge.shape == (12,)

    def test_no_sell_rate_gives_zero_csell(self) -> None:
        from samba.tariff import resolve_tariff

        arrays = resolve_tariff(self._flat_tariff(), load_kw=_SAMPLE_LOAD_KW)
        assert np.all(arrays.csell == 0.0)

    def test_flat_cbuy_all_equal(self) -> None:
        from samba.tariff import resolve_tariff

        arrays = resolve_tariff(self._flat_tariff(), load_kw=_SAMPLE_LOAD_KW)
        assert np.all(arrays.cbuy == pytest.approx(0.12))

    def test_no_service_charge_gives_zeros(self) -> None:
        from samba.tariff import resolve_tariff

        arrays = resolve_tariff(self._flat_tariff(), load_kw=_SAMPLE_LOAD_KW)
        assert np.all(arrays.service_charge == 0.0)

    def test_tou_buy_rate(self) -> None:
        from samba.tariff import resolve_tariff

        tariff = Tariff(buy=BuyRate(type="tou", tou_schedule=[_FLAT_PERIOD, _PEAK_PERIOD]))
        arrays = resolve_tariff(tariff, load_kw=_SAMPLE_LOAD_KW)
        assert arrays.cbuy.max() == pytest.approx(0.30)

    def test_flat_sell_rate(self) -> None:
        from samba.tariff import resolve_tariff

        tariff = Tariff(
            buy=BuyRate(type="flat", rate_per_kwh=0.12),
            sell=SellRate(type="flat", rate_per_kwh=0.05),
        )
        arrays = resolve_tariff(tariff, load_kw=_SAMPLE_LOAD_KW)
        assert np.all(arrays.csell == pytest.approx(0.05))

    def test_with_flat_service_charge(self) -> None:
        from samba.tariff import resolve_tariff

        tariff = Tariff(
            buy=BuyRate(type="flat", rate_per_kwh=0.12),
            service_charge=ServiceCharge(type="flat", monthly_flat=10.0),
        )
        arrays = resolve_tariff(tariff, load_kw=_SAMPLE_LOAD_KW)
        assert np.all(arrays.service_charge == pytest.approx(10.0))
