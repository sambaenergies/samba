# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for samba.tariff.endogenous tier decomposition helpers.

Covers:
- month_hour_indices() — correct lengths and index ranges
- build_tier_specs() for tiered, monthly_tiered, and seasonal_tiered
- validate_tier_specs() — accepts non-decreasing, rejects declining-block
"""

from __future__ import annotations

import math

import pytest

from samba.scenario.models import BuyRate, SeasonalTiers, TierLevel
from samba.tariff.endogenous import (
    TierSpec,
    build_tier_specs,
    month_hour_indices,
    validate_tier_specs,
)

# ---------------------------------------------------------------------------
# month_hour_indices
# ---------------------------------------------------------------------------

_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


class TestMonthHourIndices:
    def test_january_has_744_hours(self) -> None:
        assert len(month_hour_indices(0)) == 31 * 24

    def test_february_has_672_hours_nonleap(self) -> None:
        assert len(month_hour_indices(1)) == 28 * 24

    def test_july_has_744_hours(self) -> None:
        assert len(month_hour_indices(6)) == 31 * 24

    def test_december_has_744_hours(self) -> None:
        assert len(month_hour_indices(11)) == 31 * 24

    def test_all_months_total_8760_hours(self) -> None:
        total = sum(len(month_hour_indices(m)) for m in range(12))
        assert total == 8760

    def test_months_are_contiguous_and_non_overlapping(self) -> None:
        all_hours: list[int] = []
        for m in range(12):
            all_hours.extend(month_hour_indices(m))
        assert sorted(all_hours) == list(range(8760))

    def test_january_indices_start_at_zero(self) -> None:
        assert month_hour_indices(0)[0] == 0

    def test_december_indices_end_at_8759(self) -> None:
        assert month_hour_indices(11)[-1] == 8759

    def test_invalid_month_raises(self) -> None:
        with pytest.raises(ValueError, match="month must be in \\[0, 11\\]"):
            month_hour_indices(12)

    def test_negative_month_raises(self) -> None:
        with pytest.raises(ValueError):
            month_hour_indices(-1)

    def test_each_month_has_correct_length(self) -> None:
        for m, days in enumerate(_DAYS_IN_MONTH):
            assert len(month_hour_indices(m)) == days * 24


# ---------------------------------------------------------------------------
# build_tier_specs — tiered
# ---------------------------------------------------------------------------


def _make_tiered_buy(rates: list[float], limits: list[float | None] | None = None) -> BuyRate:
    """Create a simple tiered BuyRate.  Last tier has limit_kwh=None."""
    if limits is None:
        # Auto-generate equal-width tiers, final one unbounded
        limits = [500.0 * (i + 1) for i in range(len(rates) - 1)] + [None]
    tiers = [
        TierLevel(limit_kwh=lim, rate_per_kwh=r) for lim, r in zip(limits, rates, strict=False)
    ]
    return BuyRate(type="tiered", tiers=tiers)


class TestBuildTierSpecsTiered:
    def test_returns_12_specs(self) -> None:
        buy = _make_tiered_buy([0.10, 0.15, 0.20])
        specs = build_tier_specs(buy)
        assert len(specs) == 12

    def test_month_indices_correct(self) -> None:
        buy = _make_tiered_buy([0.10, 0.20])
        specs = build_tier_specs(buy)
        for m, spec in enumerate(specs):
            assert spec.month == m

    def test_all_months_identical_for_flat_tiered(self) -> None:
        buy = _make_tiered_buy([0.10, 0.15, 0.20])
        specs = build_tier_specs(buy)
        assert all(s.rates == specs[0].rates for s in specs)
        assert all(s.boundaries == specs[0].boundaries for s in specs)

    def test_rates_correct(self) -> None:
        buy = _make_tiered_buy([0.08, 0.14, 0.22])
        specs = build_tier_specs(buy)
        assert specs[0].rates == [0.08, 0.14, 0.22]

    def test_boundaries_correct(self) -> None:
        buy = _make_tiered_buy([0.10, 0.20], limits=[500.0, None])
        specs = build_tier_specs(buy)
        assert specs[0].boundaries[0] == pytest.approx(500.0)
        assert math.isinf(specs[0].boundaries[1])

    def test_last_boundary_is_inf(self) -> None:
        buy = _make_tiered_buy([0.10, 0.15, 0.20])
        specs = build_tier_specs(buy)
        for spec in specs:
            assert math.isinf(spec.boundaries[-1])


# ---------------------------------------------------------------------------
# build_tier_specs — monthly_tiered
# ---------------------------------------------------------------------------


class TestBuildTierSpecsMonthlyTiered:
    def _make_buy(self) -> BuyRate:
        # Jan–Jun low rates, Jul–Dec high rates
        low_tiers = [TierLevel(limit_kwh=500, rate_per_kwh=0.08), TierLevel(rate_per_kwh=0.12)]
        high_tiers = [TierLevel(limit_kwh=400, rate_per_kwh=0.12), TierLevel(rate_per_kwh=0.18)]
        monthly = [low_tiers] * 6 + [high_tiers] * 6
        return BuyRate(type="monthly_tiered", monthly_tiers=monthly)

    def test_returns_12_specs(self) -> None:
        specs = build_tier_specs(self._make_buy())
        assert len(specs) == 12

    def test_summer_months_have_higher_rates(self) -> None:
        specs = build_tier_specs(self._make_buy())
        # January (index 0) should have lower rates than July (index 6)
        assert specs[0].rates[0] < specs[6].rates[0]

    def test_each_month_has_own_boundaries(self) -> None:
        specs = build_tier_specs(self._make_buy())
        assert specs[0].boundaries[0] == pytest.approx(500.0)
        assert specs[6].boundaries[0] == pytest.approx(400.0)


# ---------------------------------------------------------------------------
# build_tier_specs — seasonal_tiered
# ---------------------------------------------------------------------------


class TestBuildTierSpecsSeasonalTiered:
    def _make_buy(self) -> BuyRate:
        winter_tiers = [TierLevel(limit_kwh=600, rate_per_kwh=0.09), TierLevel(rate_per_kwh=0.14)]
        summer_tiers = [TierLevel(limit_kwh=350, rate_per_kwh=0.13), TierLevel(rate_per_kwh=0.21)]
        return BuyRate(
            type="seasonal_tiered",
            seasonal_tiers=[
                SeasonalTiers(name="winter", months=[1, 2, 3, 10, 11, 12], tiers=winter_tiers),
                SeasonalTiers(name="summer", months=[4, 5, 6, 7, 8, 9], tiers=summer_tiers),
            ],
        )

    def test_returns_12_specs(self) -> None:
        specs = build_tier_specs(self._make_buy())
        assert len(specs) == 12

    def test_winter_months_have_lower_rates(self) -> None:
        specs = build_tier_specs(self._make_buy())
        # January (index 0) = winter; April (index 3) = summer
        assert specs[0].rates[0] < specs[3].rates[0]

    def test_summer_months_have_lower_boundaries(self) -> None:
        specs = build_tier_specs(self._make_buy())
        assert specs[3].boundaries[0] == pytest.approx(350.0)
        assert specs[0].boundaries[0] == pytest.approx(600.0)

    def test_uncovered_month_gets_zero_tier(self) -> None:
        """If a month is not covered by any season, a zero-rate fallback is used."""
        # Only define one season, leaving some months uncovered
        buy = BuyRate(
            type="seasonal_tiered",
            seasonal_tiers=[
                SeasonalTiers(
                    name="summer",
                    months=[6, 7, 8],
                    tiers=[
                        TierLevel(limit_kwh=500, rate_per_kwh=0.15),
                        TierLevel(rate_per_kwh=0.22),
                    ],
                )
            ],
        )
        specs = build_tier_specs(buy)
        # January (index 0) is not covered
        assert specs[0].rates == [0.0]
        assert math.isinf(specs[0].boundaries[0])

    def test_unsupported_type_raises(self) -> None:
        buy = BuyRate(type="flat", rate_per_kwh=0.15)
        with pytest.raises(ValueError, match="unsupported tariff type"):
            build_tier_specs(buy)


# ---------------------------------------------------------------------------
# validate_tier_specs
# ---------------------------------------------------------------------------


class TestValidateTierSpecs:
    def test_non_decreasing_rates_pass(self) -> None:
        specs = [
            TierSpec(month=m, boundaries=[500.0, float("inf")], rates=[0.10, 0.20])
            for m in range(12)
        ]
        validate_tier_specs(specs)  # must not raise

    def test_equal_rates_pass(self) -> None:
        specs = [
            TierSpec(month=m, boundaries=[500.0, float("inf")], rates=[0.15, 0.15])
            for m in range(12)
        ]
        validate_tier_specs(specs)  # must not raise

    def test_single_tier_passes(self) -> None:
        specs = [TierSpec(month=m, boundaries=[float("inf")], rates=[0.12]) for m in range(12)]
        validate_tier_specs(specs)

    def test_declining_block_raises(self) -> None:
        specs = [
            TierSpec(month=m, boundaries=[500.0, 1000.0, float("inf")], rates=[0.15, 0.12, 0.10])
            for m in range(12)
        ]
        with pytest.raises(ValueError, match="non-decreasing tier rates"):
            validate_tier_specs(specs)

    def test_declining_block_error_mentions_month_and_tier(self) -> None:
        """Error message must identify the exact month and tier pair."""
        specs = [
            TierSpec(month=m, boundaries=[500.0, float("inf")], rates=[0.10, 0.08])
            for m in range(12)
        ]
        with pytest.raises(ValueError) as exc_info:
            validate_tier_specs(specs)
        msg = str(exc_info.value)
        assert "month 0" in msg
        assert "tier 1" in msg

    def test_declining_block_error_mentions_use_v1(self) -> None:
        specs = [
            TierSpec(month=m, boundaries=[float("inf"), float("inf")], rates=[0.20, 0.10])
            for m in range(12)
        ]
        with pytest.raises(ValueError, match="endogenous_tiering=False"):
            validate_tier_specs(specs)
