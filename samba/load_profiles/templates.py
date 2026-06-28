# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Built-in load-profile templates (v4 Phase 26).

Provides stylised residential / commercial / industrial hourly shapes so users
without metered data can start from a sensible profile scaled to an annual energy
total. The shapes are generated **algorithmically** (deterministic, no bundled
data files and no third-party data provenance) from hour-of-day, day-of-week, and
seasonal factors. They are representative, not metered ground truth.
"""

from __future__ import annotations

import numpy as np

__all__ = ["TEMPLATE_NAMES", "build_template_profile", "build_load_from_template"]

HOURS_PER_YEAR = 8760

TEMPLATE_NAMES = ("residential", "commercial", "industrial")


def _calendar() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (hour_of_day 0-23, day_of_year 0-364, is_weekend) for 8760 hours.

    Day-of-week uses a fixed reference where hour 0 is a Monday, so the pattern is
    deterministic and independent of any real calendar year.
    """
    h = np.arange(HOURS_PER_YEAR)
    hour_of_day = h % 24
    day_index = h // 24
    day_of_year = day_index % 365
    is_weekend = (day_index % 7) >= 5  # day 0 = Monday -> days 5,6 = Sat,Sun
    return hour_of_day, day_of_year, is_weekend


def _winter_summer_season(day_of_year: np.ndarray) -> np.ndarray:
    """A 1.0-mean seasonal multiplier peaking in winter and summer (two humps)."""
    # cos with period of half a year gives peaks near Jan and Jul.
    return 1.0 + 0.20 * np.cos(4.0 * np.pi * (day_of_year - 15) / 365.0)


def build_template_profile(name: str) -> np.ndarray:
    """Return an ``(8760,)`` normalised load shape (mean 1.0) for *name*.

    Raises ``ValueError`` for an unknown template name.
    """
    if name not in TEMPLATE_NAMES:
        raise ValueError(f"unknown load template {name!r}; choose from {', '.join(TEMPLATE_NAMES)}")

    hod, doy, weekend = _calendar()
    season = _winter_summer_season(doy)

    if name == "residential":
        # Morning (7-9) and evening (18-22) peaks; higher on weekends; seasonal.
        base = (
            0.5 + 0.25 * np.exp(-((hod - 8) ** 2) / 4.0) + 0.55 * np.exp(-((hod - 20) ** 2) / 6.0)
        )
        weekend_factor = np.where(weekend, 1.12, 1.0)
        shape = base * weekend_factor * season

    elif name == "commercial":
        # Weekday daytime (8-18) plateau; low overnight and on weekends.
        daytime = ((hod >= 8) & (hod <= 18)).astype(np.float64)
        base = 0.25 + 0.85 * daytime
        weekend_factor = np.where(weekend, 0.45, 1.0)
        shape = base * weekend_factor * season

    else:  # industrial
        # High flat baseload with a mild daytime shift; slightly lower weekends.
        base = 0.85 + 0.15 * ((hod >= 6) & (hod <= 22)).astype(np.float64)
        weekend_factor = np.where(weekend, 0.92, 1.0)
        shape = base * weekend_factor * (0.5 * season + 0.5)  # damped seasonality

    # Normalise to mean 1.0 so downstream scaling is by annual energy.
    return np.asarray(shape / shape.mean(), dtype=np.float64)


def build_load_from_template(name: str, annual_kwh: float) -> np.ndarray:
    """Return an ``(8760,)`` load [kW] for *name* scaled to *annual_kwh* [kWh/yr]."""
    if annual_kwh <= 0.0:
        raise ValueError("template load requires annual_kwh > 0")
    shape = build_template_profile(name)
    # Mean is 1.0, so total = 8760; scale so the year sums to annual_kwh.
    return np.asarray(shape * (annual_kwh / shape.sum()), dtype=np.float64)


def build_generic_shape(peak_month: str) -> np.ndarray:
    """Return an ``(8760,)`` normalised generic load shape (mean 1.0).

    A residential-style daily double-peak modulated by a single seasonal hump,
    peaking in **summer** when ``peak_month`` is ``"July"`` and in **winter**
    otherwise. Generated algorithmically (no data files); used by the
    ``generic_*`` load sources.
    """
    hod, doy, _weekend = _calendar()
    daily = 0.55 + 0.30 * np.exp(-((hod - 8) ** 2) / 5.0) + 0.50 * np.exp(-((hod - 19) ** 2) / 6.0)
    if peak_month.strip().lower() == "july":
        seasonal = 1.0 + 0.30 * np.cos(2.0 * np.pi * (doy - 196) / 365.0)  # peak ~mid-July
    else:
        seasonal = 1.0 + 0.30 * np.cos(2.0 * np.pi * (doy - 15) / 365.0)  # peak ~mid-January
    shape = daily * seasonal
    return np.asarray(shape / shape.mean(), dtype=np.float64)
