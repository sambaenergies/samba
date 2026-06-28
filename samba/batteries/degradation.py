# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Battery capacity-fade / degradation model (v4).

Converts the solved annual discharge throughput into an effective battery
lifetime, so replacement economics reflect how hard the battery is cycled rather
than a fixed nameplate ``lifetime_years``. The fade model is intentionally simple
and linear (documented as an approximation in ``docs/known-limitations.md``):

    annual_fade_pct = calendar_fade_pct_yr + cycle_fade_pct_per_efc x EFC_per_year
    years_to_eol    = (100 - end_of_life_capacity_pct) / annual_fade_pct
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from samba.scenario.models import BatteryDegradation

__all__ = [
    "annual_equivalent_full_cycles",
    "effective_battery_lifetime_years",
]


def annual_equivalent_full_cycles(annual_discharge_kwh: float, capacity_kwh: float) -> float:
    """Equivalent full cycles per year = annual discharge throughput / usable capacity."""
    if capacity_kwh <= 0.0:
        return 0.0
    return float(annual_discharge_kwh) / float(capacity_kwh)


def effective_battery_lifetime_years(
    degradation: BatteryDegradation,
    annual_discharge_kwh: float,
    capacity_kwh: float,
    nameplate_lifetime_years: float,
) -> float:
    """Return the battery's degradation-derived effective lifetime [years].

    With no modelled fade (both rates 0) the nameplate lifetime is returned
    unchanged. Otherwise the lifetime is the number of years of linear fade until
    capacity reaches ``end_of_life_capacity_pct`` of nameplate, floored at 1 year.
    """
    efc = annual_equivalent_full_cycles(annual_discharge_kwh, capacity_kwh)
    annual_fade = degradation.calendar_fade_pct_yr + degradation.cycle_fade_pct_per_efc * efc
    if annual_fade <= 0.0:
        return float(nameplate_lifetime_years)
    allowable_loss = 100.0 - degradation.end_of_life_capacity_pct
    return max(1.0, allowable_loss / annual_fade)
