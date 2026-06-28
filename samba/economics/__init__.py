# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""SAMBA economics module.

Sub-modules
-----------
npc
    Core discount-rate helpers (real discount rate, present-worth factors).
replacement
    Component replacement scheduling and NPV.
salvage
    Salvage value at end of project lifetime.
emissions
    DG fuel consumption and greenhouse-gas emission estimates.
cashflow
    Central economics orchestrator: produces the full ''economics.json''
    dictionary from a solved dispatch result.
"""

from __future__ import annotations

from samba.economics.cashflow import build_economics
from samba.economics.emissions import (
    DEFAULT_DG_EMISSION_FACTOR,
    DEFAULT_GRID_EMISSION_FACTOR,
    calc_diesel_co2_var_cost,
    calc_grid_co2_var_cost,
    dg_emissions_kg,
    dg_fuel_liters,
    grid_emissions_kg,
)
from samba.economics.npc import (
    present_worth_factor,
    real_discount_rate,
    single_payment_pv,
)
from samba.economics.replacement import replacement_count, replacement_npv, replacement_years
from samba.economics.salvage import salvage_fraction, salvage_npv

__all__ = [
    "build_economics",
    "calc_diesel_co2_var_cost",
    "calc_grid_co2_var_cost",
    "DEFAULT_DG_EMISSION_FACTOR",
    "DEFAULT_GRID_EMISSION_FACTOR",
    "dg_emissions_kg",
    "dg_fuel_liters",
    "grid_emissions_kg",
    "present_worth_factor",
    "real_discount_rate",
    "single_payment_pv",
    "replacement_count",
    "replacement_npv",
    "replacement_years",
    "salvage_fraction",
    "salvage_npv",
]
