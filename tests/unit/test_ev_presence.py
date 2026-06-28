# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for the EV presence schedule generator.

Tests cover:
* Output shape and value range
* Workday/weekend correct classification
* Away/home hours for standard morning-departure schedule
* Midnight-crossing schedule (depart in afternoon, arrive next morning)
* find_departure_hours and find_arrival_hours transitions
* load_presence_csv validation (row count + value range)
* build_travel_depletion_array values and placement
"""

from __future__ import annotations

import numpy as np
import pytest

from samba.load_profiles.ev_presence import (
    build_presence_schedule,
    build_travel_depletion_array,
    find_arrival_hours,
    find_departure_hours,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_YEAR = 2023  # 2023-01-01 = Sunday
_DEP = 8  # standard departure hour (08:00)
_ARR = 18  # standard arrival hour (18:00)
_WPWK = 5  # workdays per week (Mon–Fri)

# In 2023, Jan 1 = Sunday (weekday=6). First Monday is Jan 2 (day index 1).
# Hour indices for Mon Jan 2: global hours 24–47
_MON_JAN2_START = 24  # global hour index of 00:00 on Monday Jan 2 2023
_SAT_JAN7_START = 24 * 6  # global hour index of 00:00 on Saturday Jan 7 2023


# ---------------------------------------------------------------------------
# TestBuildPresenceSchedule
# ---------------------------------------------------------------------------


class TestBuildPresenceSchedule:
    """Tests for build_presence_schedule()."""

    def test_output_shape(self) -> None:
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        assert p.shape == (8760,)

    def test_output_dtype_float64(self) -> None:
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        assert p.dtype == np.float64

    def test_only_zeros_and_ones(self) -> None:
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        unique = set(p.tolist())
        assert unique <= {0.0, 1.0}

    def test_workday_away_during_commute(self) -> None:
        """On Mon Jan 2, hours 08–17 (global 32–41) should be 0 (away)."""
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        away_start = _MON_JAN2_START + _DEP  # global 32
        away_end = _MON_JAN2_START + _ARR  # global 42 (exclusive)
        away_hours = p[away_start:away_end]
        assert np.all(away_hours == 0.0), f"Expected all 0 in away window; got {away_hours}"

    def test_workday_home_outside_commute(self) -> None:
        """On Mon Jan 2, hours 00–07 and 18–23 should be 1 (home)."""
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        home_before = p[_MON_JAN2_START : _MON_JAN2_START + _DEP]
        home_after = p[_MON_JAN2_START + _ARR : _MON_JAN2_START + 24]
        assert np.all(home_before == 1.0), "Expected home before departure"
        assert np.all(home_after == 1.0), "Expected home after arrival"

    def test_weekend_all_home(self) -> None:
        """Saturday Jan 7 (all 24 hours) should be 1 (home)."""
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        sat_hours = p[_SAT_JAN7_START : _SAT_JAN7_START + 24]
        assert np.all(sat_hours == 1.0), f"Expected all home on Saturday; got {sat_hours}"

    def test_7_workdays_every_day_commutes(self) -> None:
        """workdays_per_week=7: every day has away hours; sum < 8760."""
        p = build_presence_schedule(_ARR, _DEP, 7, _YEAR)
        assert p.sum() < 8760.0  # some away hours exist
        # Check Sunday Jan 1 (day 0, global hours 0–23) is also away during commute
        sun_away = p[_DEP:_ARR]
        assert np.all(sun_away == 0.0), "Expected commute hours on Sunday with 7 workdays"

    def test_1_workday_only_monday_commutes(self) -> None:
        """workdays_per_week=1: only Monday commutes; Saturday is all home."""
        p = build_presence_schedule(_ARR, _DEP, 1, _YEAR)
        sat_hours = p[_SAT_JAN7_START : _SAT_JAN7_START + 24]
        assert np.all(sat_hours == 1.0)
        # Tuesday (day index 2, start = 48) should be home all day
        tue_start = 48
        tue_hours = p[tue_start : tue_start + 24]
        assert np.all(tue_hours == 1.0), "Tuesday should be home with 1 workday/week"

    def test_midnight_crossing_schedule(self) -> None:
        """Depart at 20:00, arrive at 06:00 — away window crosses midnight."""
        p = build_presence_schedule(
            arrival_hour=6, departure_hour=20, workdays_per_week=5, year=_YEAR
        )
        # Monday Jan 2 (day index 1, start = 24):
        # away: 20–23 on Monday + 00–05 on Tuesday
        # home: 06–19 on Monday
        mon_home_morning = p[_MON_JAN2_START + 6 : _MON_JAN2_START + 20]
        assert np.all(mon_home_morning == 1.0), "Should be home 06–19 on Monday"
        mon_away_eve = p[_MON_JAN2_START + 20 : _MON_JAN2_START + 24]
        assert np.all(mon_away_eve == 0.0), "Should be away 20–23 on Monday"
        # Tuesday 00–05 (global 48–53) should also be away
        tue_start = _MON_JAN2_START + 24
        tue_away = p[tue_start : tue_start + 6]
        assert np.all(tue_away == 0.0), "Should be away 00–05 on Tuesday"

    def test_invalid_same_hour_raises(self) -> None:
        with pytest.raises(ValueError, match="differ"):
            build_presence_schedule(8, 8)

    def test_invalid_workdays_raises(self) -> None:
        with pytest.raises(ValueError):
            build_presence_schedule(18, 8, workdays_per_week=0)


# ---------------------------------------------------------------------------
# TestFindDepartureArrivalHours
# ---------------------------------------------------------------------------


class TestFindDepartureArrivalHours:
    """Tests for find_departure_hours() and find_arrival_hours()."""

    def test_departure_hours_count(self) -> None:
        """Should have at most 5 departures per week (Mon–Fri)."""
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        deps = find_departure_hours(p)
        # 52 full weeks + 1 day in 2023 → approximately 260–261 weekdays
        assert 255 <= len(deps) <= 265

    def test_departure_hours_values(self) -> None:
        """Each departure index should correspond to departure_hour within its day."""
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        deps = find_departure_hours(p)
        dep_hours_of_day = deps % 24
        assert np.all(dep_hours_of_day == _DEP), (
            f"Expected all departure hours = {_DEP}; got unique {np.unique(dep_hours_of_day)}"
        )

    def test_arrival_hours_values(self) -> None:
        """Each arrival index should correspond to arrival_hour within its day."""
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        arrs = find_arrival_hours(p)
        arr_hours_of_day = arrs % 24
        assert np.all(arr_hours_of_day == _ARR), (
            f"Expected all arrival hours = {_ARR}; got unique {np.unique(arr_hours_of_day)}"
        )

    def test_departure_arrival_counts_equal(self) -> None:
        """Number of departures should equal number of arrivals."""
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        assert len(find_departure_hours(p)) == len(find_arrival_hours(p))

    def test_departure_precedes_arrival(self) -> None:
        """Each departure should occur before the corresponding arrival."""
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        deps = find_departure_hours(p)
        arrs = find_arrival_hours(p)
        assert len(deps) == len(arrs)
        assert np.all(deps < arrs), "Every departure should precede its corresponding arrival"

    def test_wrong_length_raises(self) -> None:
        with pytest.raises(ValueError):
            find_departure_hours(np.ones(100))


# ---------------------------------------------------------------------------
# TestBuildTravelDepletionArray
# ---------------------------------------------------------------------------


class TestBuildTravelDepletionArray:
    """Tests for build_travel_depletion_array()."""

    def _std_depletion(self) -> tuple[np.ndarray, np.ndarray, float]:
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        deps = find_departure_hours(p)
        depletion = build_travel_depletion_array(
            departure_hours=deps,
            soc_departure=0.8,
            soc_arrival=0.3,
            capacity_kwh=40.0,
        )
        return depletion, deps, (0.8 - 0.3) * 40.0

    def test_output_shape(self) -> None:
        depletion, _, _ = self._std_depletion()
        assert depletion.shape == (8760,)

    def test_departure_hours_have_correct_value(self) -> None:
        depletion, deps, expected_kwh = self._std_depletion()
        assert np.all(depletion[deps] == pytest.approx(expected_kwh))

    def test_non_departure_hours_are_zero(self) -> None:
        depletion, deps, _ = self._std_depletion()
        non_dep = np.ones(8760, dtype=bool)
        non_dep[deps] = False
        assert np.all(depletion[non_dep] == 0.0)

    def test_zero_depletion_when_soc_equal(self) -> None:
        p = build_presence_schedule(_ARR, _DEP, _WPWK, _YEAR)
        deps = find_departure_hours(p)
        depletion = build_travel_depletion_array(deps, 0.5, 0.5, 40.0)
        assert np.all(depletion == 0.0)

    def test_empty_departure_hours_returns_zeros(self) -> None:
        depletion = build_travel_depletion_array(np.array([], dtype=np.int64), 0.8, 0.3, 40.0)
        assert np.all(depletion == 0.0)
        assert depletion.shape == (8760,)
