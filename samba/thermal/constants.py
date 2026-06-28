# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Air-source heat-pump catalog sizes and physics-based COP parameters.

The coefficient-of-performance is modeled from first principles as a fraction
of the reversible (Carnot) limit rather than from manufacturer regression
tables, so the model is fully self-contained and citable:

* **Carnot limit** -- the maximum COP of any heat pump operating between a cold
  reservoir at ``T_cold`` and a hot reservoir at ``T_hot`` (absolute temps):
  heating ``T_hot / (T_hot - T_cold)``; cooling ``T_cold / (T_hot - T_cold)``.
  (Carnot, 1824; any engineering thermodynamics text, e.g. Moran & Shapiro,
  *Fundamentals of Engineering Thermodynamics*.)
* **Practical efficiency fraction** -- real air-source units reach roughly
  40-50 % of the Carnot COP for heating and ~30 % for cooling once compressor,
  fan, and defrost losses are included (ASHRAE *Handbook -- Fundamentals*,
  Ch. 2; typical second-law efficiencies for vapour-compression equipment).

Catalog sizes are the standard nominal residential ASHP capacities (1.5-5 ton,
where 1 ton = 12 000 BTU/hr); they are not specific to any vendor.
"""

from __future__ import annotations

__all__ = [
    "BTU_PER_KWH",
    "KELVIN_OFFSET",
    "CATALOG_SIZES_BTU",
    "CATALOG_MODEL_NAMES",
    "HEATING_SUPPLY_TEMP_C",
    "CARNOT_FRACTION_HEATING",
    "CARNOT_FRACTION_COOLING",
    "COP_FLOOR",
    "COP_CEILING",
    "MIN_TEMP_LIFT_K",
]

# ---------------------------------------------------------------------------
# Unit / scale conversions
# ---------------------------------------------------------------------------

BTU_PER_KWH: float = 3412.142  # 1 kW = 3412.142 BTU/hr (exact ISO/IEC conversion)
KELVIN_OFFSET: float = 273.15  # 0 deg C in kelvin

# ---------------------------------------------------------------------------
# Catalog model sizes
# ---------------------------------------------------------------------------
# Standard nominal residential air-source heat-pump capacities, ascending.
# 12 000 BTU/hr = 1 "ton" of refrigeration, so these span 1.5-5 tons.

CATALOG_SIZES_BTU: list[int] = [18000, 24000, 30000, 36000, 42000, 48000, 60000]

# Generic capacity labels (nominal tons of refrigeration).
CATALOG_MODEL_NAMES: dict[int, str] = {
    18000: "ASHP-1.5ton",
    24000: "ASHP-2ton",
    30000: "ASHP-2.5ton",
    36000: "ASHP-3ton",
    42000: "ASHP-3.5ton",
    48000: "ASHP-4ton",
    60000: "ASHP-5ton",
}

# ---------------------------------------------------------------------------
# Physics-based COP parameters
# ---------------------------------------------------------------------------

# Heating supply (condenser) temperature: the warm side the unit delivers heat
# to. A mid-temperature air-to-air ASHP supplies ~45 deg C air.
HEATING_SUPPLY_TEMP_C: float = 45.0

# Practical (second-law) efficiency: fraction of the Carnot COP actually
# achieved once compressor / fan / defrost losses are included.
CARNOT_FRACTION_HEATING: float = 0.45
CARNOT_FRACTION_COOLING: float = 0.30

# Physical bounds on the resulting COP. The floor enforces energy conservation
# (a heat pump never returns less than the electricity it draws); the ceiling
# caps the Carnot singularity when the temperature lift approaches zero.
COP_FLOOR: float = 1.0
COP_CEILING: float = 8.0

# Minimum temperature lift [K] used to keep the Carnot expression finite when
# the source and sink temperatures nearly coincide.
MIN_TEMP_LIFT_K: float = 1.0
