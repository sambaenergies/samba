# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for the v4 battery degradation model."""

from __future__ import annotations

import pytest

from samba.batteries.degradation import (
    annual_equivalent_full_cycles,
    effective_battery_lifetime_years,
)
from samba.scenario.models import BatteryDegradation


class TestEquivalentFullCycles:
    def test_zero_capacity_is_zero(self) -> None:
        assert annual_equivalent_full_cycles(1000.0, 0.0) == 0.0

    def test_basic_ratio(self) -> None:
        # 3650 kWh discharged from a 10 kWh battery = 365 EFC/yr (~1/day)
        assert annual_equivalent_full_cycles(3650.0, 10.0) == pytest.approx(365.0)


class TestEffectiveLifetime:
    def test_no_fade_returns_nameplate(self) -> None:
        deg = BatteryDegradation(calendar_fade_pct_yr=0.0, cycle_fade_pct_per_efc=0.0)
        assert effective_battery_lifetime_years(deg, 3650.0, 10.0, 10) == pytest.approx(10.0)

    def test_calendar_only_fade(self) -> None:
        # 2%/yr calendar fade, EOL at 80% -> 20% / 2% = 10 years
        deg = BatteryDegradation(calendar_fade_pct_yr=2.0, end_of_life_capacity_pct=80.0)
        assert effective_battery_lifetime_years(deg, 0.0, 10.0, 99) == pytest.approx(10.0)

    def test_cycling_shortens_life(self) -> None:
        deg = BatteryDegradation(
            calendar_fade_pct_yr=1.0,
            cycle_fade_pct_per_efc=0.01,
            end_of_life_capacity_pct=80.0,
        )
        light = effective_battery_lifetime_years(deg, 365.0, 10.0, 20)  # ~36.5 EFC/yr
        heavy = effective_battery_lifetime_years(deg, 3650.0, 10.0, 20)  # ~365 EFC/yr
        assert heavy < light
        # heavy: annual fade = 1 + 0.01*365 = 4.65 %/yr -> 20/4.65 ≈ 4.3 yr
        assert heavy == pytest.approx(20.0 / (1.0 + 0.01 * 365.0), rel=1e-6)

    def test_floored_at_one_year(self) -> None:
        deg = BatteryDegradation(calendar_fade_pct_yr=1000.0, end_of_life_capacity_pct=80.0)
        assert effective_battery_lifetime_years(deg, 0.0, 10.0, 10) == pytest.approx(1.0)
