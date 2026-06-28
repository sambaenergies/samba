# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for Gas tariff models and build_gas_rate_array (Phase 23)."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from samba.scenario.models import GasSeasonalRate, GasTariff
from samba.tariff.gas import build_gas_rate_array

# ---------------------------------------------------------------------------
# GasSeasonalRate validation
# ---------------------------------------------------------------------------


class TestGasSeasonalRate:
    def test_valid(self) -> None:
        r = GasSeasonalRate(months=[1, 2, 3], rate=0.05)
        assert r.months == [1, 2, 3]
        assert r.rate == pytest.approx(0.05)

    def test_empty_months_raises(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            GasSeasonalRate(months=[], rate=0.05)

    def test_invalid_month_value(self) -> None:
        with pytest.raises(ValidationError, match="1-12"):
            GasSeasonalRate(months=[0, 1], rate=0.05)

    def test_negative_rate_raises(self) -> None:
        with pytest.raises(ValidationError, match=">= 0"):
            GasSeasonalRate(months=[1], rate=-0.01)


# ---------------------------------------------------------------------------
# GasTariff validation
# ---------------------------------------------------------------------------


class TestGasTariff:
    def test_flat_valid(self) -> None:
        t = GasTariff(rate_type="flat", flat_rate=0.04)
        assert t.flat_rate == pytest.approx(0.04)
        assert t.unit == "per_kwh_th"

    def test_flat_missing_rate_raises(self) -> None:
        with pytest.raises(ValidationError, match="flat_rate is required"):
            GasTariff(rate_type="flat")

    def test_flat_negative_rate_raises(self) -> None:
        with pytest.raises(ValidationError, match="flat_rate must be >= 0"):
            GasTariff(rate_type="flat", flat_rate=-0.01)

    def test_seasonal_valid(self) -> None:
        t = GasTariff(
            rate_type="seasonal",
            seasonal_schedule=[
                GasSeasonalRate(months=[12, 1, 2], rate=0.06),
                GasSeasonalRate(months=[3, 4, 5, 6, 7, 8, 9, 10, 11], rate=0.04),
            ],
        )
        assert t.rate_type == "seasonal"

    def test_seasonal_missing_schedule_raises(self) -> None:
        with pytest.raises(ValidationError, match="seasonal_schedule is required"):
            GasTariff(rate_type="seasonal")

    def test_tiered_valid(self) -> None:
        t = GasTariff(
            rate_type="tiered",
            tiered_limits_kwh_th=[500.0, 1000.0, 1e9],
            tiered_rates=[0.03, 0.05, 0.07],
        )
        assert len(t.tiered_rates) == 3  # type: ignore[arg-type]

    def test_tiered_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValidationError, match="same length"):
            GasTariff(
                rate_type="tiered",
                tiered_limits_kwh_th=[500.0, 1000.0],
                tiered_rates=[0.03],
            )

    def test_tiered_missing_both_raises(self) -> None:
        with pytest.raises(
            ValidationError, match="tiered_limits_kwh_th and tiered_rates are required"
        ):
            GasTariff(rate_type="tiered")

    def test_negative_service_charge_raises(self) -> None:
        with pytest.raises(ValidationError, match="monthly_service_charge must be >= 0"):
            GasTariff(rate_type="flat", flat_rate=0.04, monthly_service_charge=-1.0)


# ---------------------------------------------------------------------------
# build_gas_rate_array
# ---------------------------------------------------------------------------


class TestBuildGasRateArray:
    def test_flat_kwh_th(self) -> None:
        tariff = GasTariff(rate_type="flat", flat_rate=0.05)
        arr = build_gas_rate_array(tariff)
        assert arr.shape == (8760,)
        assert np.allclose(arr, 0.05)

    def test_flat_per_gj(self) -> None:
        # 1 GJ ≈ 277.778 kWh_th → rate $/kWh_th = rate_gj / 277.778
        tariff = GasTariff(rate_type="flat", flat_rate=11.11, unit="per_gj")
        arr = build_gas_rate_array(tariff)
        expected = 11.11 / 277.778
        assert np.allclose(arr, expected, rtol=1e-4)

    def test_flat_per_therm(self) -> None:
        tariff = GasTariff(rate_type="flat", flat_rate=1.50, unit="per_therm")
        arr = build_gas_rate_array(tariff)
        expected = 1.50 / 29.3001
        assert np.allclose(arr, expected, rtol=1e-4)

    def test_seasonal_two_bands(self) -> None:
        tariff = GasTariff(
            rate_type="seasonal",
            unit="per_kwh_th",
            seasonal_schedule=[
                GasSeasonalRate(months=[12, 1, 2], rate=0.06),
                GasSeasonalRate(months=[3, 4, 5, 6, 7, 8, 9, 10, 11], rate=0.03),
            ],
        )
        arr = build_gas_rate_array(tariff)
        assert arr.shape == (8760,)
        # January = hours 0..743 (31 days × 24 = 744 hours)
        assert np.allclose(arr[0:744], 0.06)
        # April = start at March end; test any summer hour
        summer_h = (31 + 28 + 31) * 24  # start of April = hour 2160
        assert np.allclose(arr[summer_h : summer_h + 24], 0.03)

    def test_tiered_uses_first_tier(self) -> None:
        tariff = GasTariff(
            rate_type="tiered",
            unit="per_kwh_th",
            tiered_limits_kwh_th=[500.0, 1000.0, 1e9],
            tiered_rates=[0.03, 0.05, 0.07],
        )
        arr = build_gas_rate_array(tariff)
        # First-tier approximation: entire array = first rate
        assert np.allclose(arr, 0.03)

    def test_output_dtype_float(self) -> None:
        tariff = GasTariff(rate_type="flat", flat_rate=0.04)
        arr = build_gas_rate_array(tariff)
        assert arr.dtype == np.float64
