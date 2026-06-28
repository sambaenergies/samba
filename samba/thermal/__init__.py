# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Thermal-domain infrastructure for SAMBA v3.

This package provides the bus dataclasses and factory functions for the
thermal energy domain (heating, cooling, natural gas).  Physical component
builders (heat pump, thermal storage, gas supply) live in
''samba.compiler.builders'' following the same pattern as electrical builders.

Public exports
--------------
''ThermalBusSet''
    Dataclass holding optional ''solph.Bus'' objects for ''heat_bus'',
    ''cool_bus'', and ''gas_bus''.  All three default to ''None'' so that
    electrical-only scenarios are structurally identical to v2.

''build_thermal_buses''
    Factory function: reads the scenario, conditionally creates thermal buses,
    and returns a :class:'ThermalBusSet'.  Bus labels follow ADR-001:
    ''"heat_bus"'' and ''"cool_bus"'' (not ''"heating_bus"''/''"cooling_bus"'').

''COPArrays'', ''build_cop_arrays''
    Pre-computed hourly COP arrays from a physics-based (Carnot-fraction) model.

''select_catalog_model''
    HP catalog model selection by peak demand.
"""

from __future__ import annotations

from samba.thermal.buses import ThermalBusSet, build_thermal_buses
from samba.thermal.constants import (
    BTU_PER_KWH,
    CATALOG_MODEL_NAMES,
    CATALOG_SIZES_BTU,
)
from samba.thermal.cop import COPArrays, build_cop_arrays
from samba.thermal.hp_catalog import (
    get_cooling_capacity_kw,
    get_heating_capacity_kw,
    select_catalog_model,
)

__all__ = [
    "ThermalBusSet",
    "build_thermal_buses",
    "BTU_PER_KWH",
    "CATALOG_MODEL_NAMES",
    "CATALOG_SIZES_BTU",
    "COPArrays",
    "build_cop_arrays",
    "select_catalog_model",
    "get_heating_capacity_kw",
    "get_cooling_capacity_kw",
]
