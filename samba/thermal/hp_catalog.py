# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Heat pump catalog model selection.

Picks the smallest standard nominal model whose rated capacity (BTU/hr) meets
the peak thermal demand -- ordinary "size up to the next stock unit" logic. If
no catalog model is large enough, raise ``ValueError``.

Catalog maximum: 60 000 BTU/hr (~17.6 kW).  For larger commercial systems use
``HeatPump(sizing='fixed', heating_capacity_kw=..., cooling_capacity_kw=...)``.
"""

from __future__ import annotations

import logging

from samba.thermal.constants import BTU_PER_KWH, CATALOG_MODEL_NAMES, CATALOG_SIZES_BTU

log = logging.getLogger(__name__)

__all__ = [
    "select_catalog_model",
    "get_heating_capacity_kw",
    "get_cooling_capacity_kw",
]


def select_catalog_model(peak_demand_kw: float) -> int:
    """Return the BTU/hr rating of the smallest catalog model that covers *peak_demand_kw*.

    Parameters
    ----------
    peak_demand_kw:
        Peak thermal demand in kW (heating or cooling, use the larger of the two
        when both modes are active).

    Returns
    -------
    int
        Catalog rating in BTU/hr (one of 18 000, 24 000, ..., 60 000).

    Raises
    ------
    ValueError
        If *peak_demand_kw* exceeds the largest catalog model (~17.6 kW).
    """
    if peak_demand_kw <= 0.0:
        # No thermal load configured yet (e.g. Phase 20 before Phase 22).
        # Default to smallest model so the LP topology is valid.
        selected = CATALOG_SIZES_BTU[0]
        log.debug(
            "Heat pump catalog: peak_demand_kw=%.1f kW (no load configured) -> %d BTU/hr (%s)",
            peak_demand_kw,
            selected,
            CATALOG_MODEL_NAMES[selected],
        )
        return selected

    demand_btu = peak_demand_kw * BTU_PER_KWH
    for size_btu in CATALOG_SIZES_BTU:
        if size_btu >= demand_btu:
            log.debug(
                "Heat pump catalog: peak=%.1f kW (%.0f BTU/hr) -> model %d BTU/hr (%s)",
                peak_demand_kw,
                demand_btu,
                size_btu,
                CATALOG_MODEL_NAMES[size_btu],
            )
            return size_btu

    max_kw = CATALOG_SIZES_BTU[-1] / BTU_PER_KWH
    raise ValueError(
        f"Heat pump peak demand {peak_demand_kw:.1f} kW exceeds the largest catalog model "
        f"({max_kw:.1f} kW / {CATALOG_SIZES_BTU[-1]} BTU/hr).  "
        "Use HeatPump(sizing='fixed', heating_capacity_kw=..., cooling_capacity_kw=...) "
        "for larger systems."
    )


def get_heating_capacity_kw(model_btu: int) -> float:
    """Return rated heating capacity in kW for a given catalog model.

    Parameters
    ----------
    model_btu:
        Catalog rating in BTU/hr (e.g. 36000).

    Returns
    -------
    float
        Rated capacity in kW.
    """
    return model_btu / BTU_PER_KWH


def get_cooling_capacity_kw(model_btu: int) -> float:
    """Return rated cooling capacity in kW for a given catalog model.

    The catalog rates each unit at the same nominal BTU/hr for both heating and
    cooling (conservative: the larger mode governs model selection).

    Parameters
    ----------
    model_btu:
        Catalog rating in BTU/hr.

    Returns
    -------
    float
        Rated capacity in kW.
    """
    return model_btu / BTU_PER_KWH
