# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""EV presence schedule generator.

Converts a weekly commute pattern (departure hour, arrival hour, working days
per week) into an 8 760-element binary array suitable for gating EV charge and
discharge flows in the oemof energy system model.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

__all__ = [
    "build_presence_schedule",
    "build_travel_depletion_array",
    "find_arrival_hours",
    "find_departure_hours",
    "load_presence_csv",
]


def build_presence_schedule(
    arrival_hour: int,
    departure_hour: int,
    workdays_per_week: int = 5,
    year: int = 2023,
) -> np.ndarray:
    """Return a ''(8760,)'' float64 array of EV home/away status.

    Values are ''1.0'' (EV is home and plugged in) or ''0.0'' (EV is away).

    On **workdays** the EV commutes: it is away from *departure_hour* until
    *arrival_hour* (exclusive) on the same calendar day.  If
    ''departure_hour > arrival_hour'' the away window wraps past midnight.
    On non-workdays the EV is home all day.

    "Workdays" are the first *workdays_per_week* weekdays of each week:
    Monday = 0, Tuesday = 1, ...  With ''workdays_per_week=5'' the schedule is
    the conventional Monday-to-Friday commute.

    Parameters
    ----------
    arrival_hour:
        Hour (0-23) when the EV returns home on workdays.
    departure_hour:
        Hour (0-23) when the EV leaves home on workdays.
    workdays_per_week:
        Number of days per week the EV commutes.  Must be in [1, 7].
    year:
        Calendar year (used to determine weekday layout and leap years).
        Non-leap year -> exactly 8760 hours; leap-year trailing hours trimmed
        to 8760.

    Returns
    -------
    np.ndarray, shape ''(8760,)'' dtype float64
        ''1.0'' when EV is home; ''0.0'' when away.
    """
    if not (0 <= arrival_hour <= 23):
        raise ValueError("arrival_hour must be in [0, 23]")
    if not (0 <= departure_hour <= 23):
        raise ValueError("departure_hour must be in [0, 23]")
    if arrival_hour == departure_hour:
        raise ValueError("arrival_hour and departure_hour must differ")
    if not (1 <= workdays_per_week <= 7):
        raise ValueError("workdays_per_week must be in [1, 7]")

    presence = np.ones(8760, dtype=np.float64)
    start_date = datetime(year, 1, 1)
    workday_set = set(range(workdays_per_week))  # 0=Mon, 1=Tue, ...

    for d in range(365):
        current_date = start_date + timedelta(days=d)
        if current_date.weekday() not in workday_set:
            continue  # weekend / non-workday -> EV home all day

        day_start = 24 * d  # global hour index of 00:00 for this day

        if departure_hour < arrival_hour:
            # Away window within same day: departure_hour to arrival_hour-1
            away_slice = slice(day_start + departure_hour, day_start + arrival_hour)
            presence[away_slice] = 0.0
        else:
            # Away window wraps midnight: departure_hour to end of day ...
            presence[day_start + departure_hour : day_start + 24] = 0.0
            # ... and 00:00 to arrival_hour-1 the FOLLOWING day (clipped to 8760)
            next_day_start = day_start + 24
            end_idx = min(next_day_start + arrival_hour, 8760)
            if next_day_start < 8760:
                presence[next_day_start:end_idx] = 0.0

    return presence


def load_presence_csv(path: str | Path) -> np.ndarray:
    """Load a presence array from a single-column CSV file.

    The CSV must have exactly one column named ''presence'' with 8 760 rows of
    0 or 1 integer values.

    Parameters
    ----------
    path:
        Absolute or relative path to the CSV file.

    Returns
    -------
    np.ndarray, shape ''(8760,)'' dtype float64
    """
    import csv

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Presence CSV not found: {p}")

    rows: list[float] = []
    with p.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or "presence" not in reader.fieldnames:
            raise ValueError(f"Presence CSV '{p}' must have a 'presence' column header")
        for row in reader:
            val = float(row["presence"])
            if val not in (0.0, 1.0):
                raise ValueError(f"Presence CSV values must be 0 or 1; got {val!r} in '{p}'")
            rows.append(val)

    if len(rows) != 8760:
        raise ValueError(f"Presence CSV must have exactly 8760 data rows; got {len(rows)} in '{p}'")

    return np.array(rows, dtype=np.float64)


def find_departure_hours(presence: np.ndarray) -> np.ndarray:
    """Return the global hour indices where the EV transitions from home -> away.

    A departure occurs at hour *t* when ''presence[t] == 0.0'' and
    ''presence[t-1] == 1.0''.

    Parameters
    ----------
    presence:
        ''(8760,)'' array from :func:'build_presence_schedule'.

    Returns
    -------
    np.ndarray, dtype int64
        Sorted array of departure hour indices.
    """
    if len(presence) != 8760:
        raise ValueError("presence must have 8760 elements")
    is_away = (presence == 0.0).astype(np.int8)
    transitions = np.diff(is_away, prepend=is_away[0])
    departures: np.ndarray = np.where(transitions == 1)[0].astype(np.int64)
    return departures


def find_arrival_hours(presence: np.ndarray) -> np.ndarray:
    """Return the global hour indices where the EV transitions from away -> home.

    An arrival occurs at hour *t* when ''presence[t] == 1.0'' and
    ''presence[t-1] == 0.0''.

    Parameters
    ----------
    presence:
        ''(8760,)'' array from :func:'build_presence_schedule'.

    Returns
    -------
    np.ndarray, dtype int64
        Sorted array of arrival hour indices.
    """
    if len(presence) != 8760:
        raise ValueError("presence must have 8760 elements")
    is_home = (presence == 1.0).astype(np.int8)
    transitions = np.diff(is_home, prepend=is_home[0])
    arrivals: np.ndarray = np.where(transitions == 1)[0].astype(np.int64)
    return arrivals


def build_travel_depletion_array(
    departure_hours: np.ndarray,
    soc_departure: float,
    soc_arrival: float,
    capacity_kwh: float,
) -> np.ndarray:
    """Return ''(8760,)'' array of forced EV energy depletion at departure hours.

    The depletion at each departure hour equals the energy consumed for travel:
    ''(soc_departure - soc_arrival) x capacity_kwh'' kWh.  All other hours are
    zero.

    Parameters
    ----------
    departure_hours:
        Array of departure hour indices from :func:'find_departure_hours'.
    soc_departure:
        Required state-of-charge when the EV departs (fraction, 0-1).
    soc_arrival:
        State-of-charge on return home (fraction, 0-1).
    capacity_kwh:
        EV battery usable capacity [kWh].

    Returns
    -------
    np.ndarray, shape ''(8760,)'' dtype float64
        Depletion in kWh (= kW for a 1-hour timestep) at each departure hour.
    """
    depletion = np.zeros(8760, dtype=np.float64)
    energy_per_trip = (soc_departure - soc_arrival) * capacity_kwh
    if energy_per_trip > 0 and len(departure_hours) > 0:
        valid = departure_hours[(departure_hours >= 0) & (departure_hours < 8760)]
        depletion[valid] = energy_per_trip
    return depletion
