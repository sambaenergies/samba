# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Natural gas unit conversion constants.

All energy quantities inside SAMBA use kWh_th (thermal kWh, lower heating
value basis).  This module provides conversion factors from common gas billing
units to kWh_th so that user-supplied rates ($/GJ, $/Mcf, $/therm) can be
normalised to $/kWh_th before being passed to the LP objective.

LHV (lower heating value) convention
-------------------------------------
SAMBA uses LHV throughout for consistency with boiler efficiency ratings, which
are virtually always quoted on an LHV basis in residential/commercial contexts.
If a user supplies an HHV-based CO₂ emission factor they should multiply by
``LHV/HHV ≈ 0.9`` before entering it in the scenario.

Conversion factors
------------------
- 1 GJ  = 277.778 kWh  (exact: 10⁶ / 3600)
- 1 Mcf (thousand cubic feet of natural gas) ≈ 293.0 kWh_th (LHV)
- 1 therm = 29.3001 kWh_th (LHV) — by definition (29.3001 × 1000 BTU LHV/therm)
"""

from __future__ import annotations

__all__ = ["GAS_UNIT_TO_KWH_TH", "convert_gas_rate"]

# Multiply a rate in $/unit by this factor to get $/kWh_th.
GAS_UNIT_TO_KWH_TH: dict[str, float] = {
    "per_kwh_th": 1.0,
    "per_gj": 1.0 / 277.778,  # 1 GJ = 277.778 kWh_th (LHV)
    "per_mcf": 1.0 / 293.001,  # 1 Mcf ≈ 293.0 kWh_th (LHV)
    "per_therm": 1.0 / 29.3001,  # 1 therm ≈ 29.3 kWh_th (LHV)
}


def convert_gas_rate(rate: float, unit: str) -> float:
    """Convert a gas rate from ``$/unit`` to ``$/kWh_th``.

    Parameters
    ----------
    rate:
        Gas price in the original billing unit.
    unit:
        Billing unit string matching a key in :data:`GAS_UNIT_TO_KWH_TH`.

    Returns
    -------
    float
        Gas price in $/kWh_th.

    Raises
    ------
    KeyError
        If *unit* is not a recognised billing unit.
    """
    return rate * GAS_UNIT_TO_KWH_TH[unit]
