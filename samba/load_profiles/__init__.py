# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Load profile processing: CSV reading, generic profiles, and 8760 expansion."""

from samba.load_profiles.ev_presence import (
    build_presence_schedule,
    build_travel_depletion_array,
    find_arrival_hours,
    find_departure_hours,
    load_presence_csv,
)
from samba.load_profiles.expander import DAYS_IN_MONTH, expand_load
from samba.load_profiles.generic import (
    build_generic_load_from_annual_total,
    build_generic_load_from_monthly,
    build_generic_load_normalized,
)

__all__ = [
    "DAYS_IN_MONTH",
    "expand_load",
    "build_generic_load_from_monthly",
    "build_generic_load_from_annual_total",
    "build_generic_load_normalized",
    "build_presence_schedule",
    "build_travel_depletion_array",
    "find_arrival_hours",
    "find_departure_hours",
    "load_presence_csv",
]
