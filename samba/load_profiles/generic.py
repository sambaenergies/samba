# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Generic load profile builder.

Two normalised annual shapes (summer-peaked and winter-peaked) are generated
algorithmically by :func:`samba.load_profiles.templates.build_generic_shape`;
callers supply a target to scale the profile to.
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _generic_shape(peak_month: str) -> np.ndarray:
    """Return the normalised 8 760-element generic load shape.

    ``"July"`` -> summer-peaked; anything else -> winter/January-peaked. Generated
    algorithmically (no data files).
    """
    from samba.load_profiles.templates import build_generic_shape

    return build_generic_shape(peak_month)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_generic_load_from_monthly(
    peak_month: str,
    monthly_totals_kwh: list[float],
) -> np.ndarray:
    """Scale the generic shape profile to match per-month kWh totals.

    Scales each month of the generic shape independently to its target.

    Parameters
    ----------
    peak_month:
        ''"July"'' or ''"January"''; selects the underlying shape profile.
    monthly_totals_kwh:
        12-element list of target monthly energy consumption [kWh].

    Returns
    -------
    np.ndarray, shape (8760,)
        Hourly load profile [kW].
    """
    if len(monthly_totals_kwh) != 12:
        raise ValueError(f"monthly_totals_kwh must have 12 elements, got {len(monthly_totals_kwh)}")
    shape = _generic_shape(peak_month)
    result = np.empty(8760, dtype=np.float64)
    start = 0
    for m, days in enumerate(_DAYS_IN_MONTH):
        end = start + 24 * days
        segment = shape[start:end]
        seg_sum = float(np.sum(segment))
        factor = monthly_totals_kwh[m] / seg_sum if seg_sum > 0 else 0.0
        result[start:end] = segment * factor
        start = end
    return result


def build_generic_load_from_annual_total(
    peak_month: str,
    annual_total_kwh: float,
) -> np.ndarray:
    """Scale the generic shape profile to match a single annual kWh total.

    Scales the generic shape to a single annual-energy target.

    Parameters
    ----------
    peak_month:
        ''"July"'' or ''"January"''; selects the underlying shape profile.
    annual_total_kwh:
        Target annual energy consumption [kWh].

    Returns
    -------
    np.ndarray, shape (8760,)
        Hourly load profile [kW].
    """
    shape = _generic_shape(peak_month)
    total = float(np.sum(shape))
    factor = annual_total_kwh / total if total > 0 else 0.0
    return shape * factor


def build_generic_load_normalized(peak_month: str) -> np.ndarray:
    """Return the raw normalised generic load shape (no scaling).

    Returns the raw normalised generic shape (caller scales it).

    Parameters
    ----------
    peak_month:
        ''"July"'' or ''"January"''; selects the underlying shape profile.

    Returns
    -------
    np.ndarray, shape (8760,)
        Normalised hourly load profile [kW] (sum = profile total, not 1.0).
    """
    return _generic_shape(peak_month).copy()
