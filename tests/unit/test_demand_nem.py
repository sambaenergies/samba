# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for the v4 demand-charge and NEM reconciliation math."""

from __future__ import annotations

import numpy as np
import pytest

from samba.tariff.demand import (
    HOURS_PER_YEAR,
    annual_demand_charge,
    hour_month_index,
    monthly_peak_import,
    nem_annual_grid_cost,
)


class TestHourMonthIndex:
    def test_length_and_range(self) -> None:
        idx = hour_month_index()
        assert idx.shape == (HOURS_PER_YEAR,)
        assert idx.min() == 0 and idx.max() == 11

    def test_month_boundaries(self) -> None:
        idx = hour_month_index()
        assert idx[0] == 0  # first hour is January
        assert idx[31 * 24 - 1] == 0  # last hour of January
        assert idx[31 * 24] == 1  # first hour of February
        assert idx[-1] == 11  # last hour is December

    def test_each_month_hour_count(self) -> None:
        idx = hour_month_index()
        counts = np.bincount(idx, minlength=12)
        days = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
        np.testing.assert_array_equal(counts, days * 24)


class TestMonthlyPeakImport:
    def test_uniform_import(self) -> None:
        peaks = monthly_peak_import(np.full(HOURS_PER_YEAR, 4.0))
        np.testing.assert_allclose(peaks, np.full(12, 4.0))

    def test_single_spike_in_one_month(self) -> None:
        gb = np.full(HOURS_PER_YEAR, 2.0)
        gb[100] = 17.0  # January (hour 100 < 744)
        peaks = monthly_peak_import(gb)
        assert peaks[0] == 17.0
        assert peaks[1] == 2.0

    def test_hours_restriction(self) -> None:
        gb = np.full(HOURS_PER_YEAR, 1.0)
        # big import only at hour-of-day 3, which is excluded by the window
        gb[np.arange(HOURS_PER_YEAR) % 24 == 3] = 50.0
        peaks = monthly_peak_import(gb, hours=[17, 18, 19])
        np.testing.assert_allclose(peaks, np.full(12, 1.0))


class TestAnnualDemandCharge:
    def test_zero_rate_is_free(self) -> None:
        assert annual_demand_charge(np.full(HOURS_PER_YEAR, 10.0), 0.0) == 0.0

    def test_uniform_peak(self) -> None:
        # 10 kW every hour, $/kW-month = 5 -> 12 months * 10 kW * 5 = 600
        assert annual_demand_charge(np.full(HOURS_PER_YEAR, 10.0), 5.0) == pytest.approx(600.0)


class TestNEMReconciliation:
    def _two_month_arrays(self, jan_buy: float, jan_sell: float, feb_buy: float, feb_sell: float):
        """Constant kW arrays so monthly $ = kW * hours_in_month * price (price=1)."""
        gb = np.zeros(HOURS_PER_YEAR)
        gs = np.zeros(HOURS_PER_YEAR)
        cb = np.ones(HOURS_PER_YEAR)
        cs = np.ones(HOURS_PER_YEAR)
        idx = hour_month_index()
        gb[idx == 0] = jan_buy
        gs[idx == 0] = jan_sell
        gb[idx == 1] = feb_buy
        gs[idx == 1] = feb_sell
        return gb, gs, cb, cs

    def test_no_export_equals_annual_netting(self) -> None:
        # Pure import both months -> NEM net == simple bought-sold.
        gb, gs, cb, cs = self._two_month_arrays(2.0, 0.0, 3.0, 0.0)
        nem = nem_annual_grid_cost(gb, gs, cb, cs)
        simple = float(np.dot(gb, cb) - np.dot(gs, cs))
        assert nem == pytest.approx(simple)

    def test_month_bill_floored_at_zero(self) -> None:
        # January net-exports heavily; without a floor it would be a big negative
        # bill. With the floor (and no carryover/credit payout) Jan contributes 0.
        gb, gs, cb, cs = self._two_month_arrays(0.0, 5.0, 4.0, 0.0)  # Jan export, Feb import
        feb_hours = int((hour_month_index() == 1).sum())
        nem = nem_annual_grid_cost(
            gb, gs, cb, cs, carryover=False, annual_excess_credit_fraction=0.0
        )
        # Jan floored to 0; Feb = 4 kW * feb_hours. No credit carried.
        assert nem == pytest.approx(4.0 * feb_hours)

    def test_carryover_credit_reduces_later_bill(self) -> None:
        # Jan surplus credit carries to Feb and offsets Feb's import bill.
        gb, gs, cb, cs = self._two_month_arrays(0.0, 5.0, 4.0, 0.0)
        jan_hours = int((hour_month_index() == 0).sum())
        feb_hours = int((hour_month_index() == 1).sum())
        nem = nem_annual_grid_cost(
            gb, gs, cb, cs, carryover=True, annual_excess_credit_fraction=0.0
        )
        # Jan credit = 5*jan_hours; Feb bill = 4*feb_hours; net = max(0, 4*feb - 5*jan)
        expected = max(0.0, 4.0 * feb_hours - 5.0 * jan_hours)
        assert nem == pytest.approx(expected)

    def test_annual_excess_credit_payout(self) -> None:
        # Large Jan export, small Feb import; leftover credit paid out at fraction 1.0.
        gb, gs, cb, cs = self._two_month_arrays(0.0, 10.0, 1.0, 0.0)
        jan_hours = int((hour_month_index() == 0).sum())
        feb_hours = int((hour_month_index() == 1).sum())
        nem_forfeit = nem_annual_grid_cost(gb, gs, cb, cs, annual_excess_credit_fraction=0.0)
        nem_payout = nem_annual_grid_cost(gb, gs, cb, cs, annual_excess_credit_fraction=1.0)
        # Forfeit: bill floored to 0 every month -> 0 total.
        assert nem_forfeit == pytest.approx(0.0)
        # Payout: customer is paid the leftover credit (negative cost).
        leftover = 10.0 * jan_hours - 1.0 * feb_hours
        assert nem_payout == pytest.approx(-leftover)
        assert nem_payout < nem_forfeit
