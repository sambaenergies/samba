# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Monthly service / standing charge calculators.

Returns a 12-element numpy array (one value per calendar month) in $/month.

Demand-based service charges are out of scope for SAMBA v1-v2 and are deferred
to v3+.  Only flat and tiered-by-kWh variants are implemented here.

Computes the fixed monthly service-charge array.
"""

from __future__ import annotations

import numpy as np

from samba.scenario.models import ServiceCharge, TierLevel

_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def calc_service_charge(
    config: ServiceCharge,
    load_kw: np.ndarray | None = None,
) -> np.ndarray:
    """Return a 12-element monthly service-charge array [$/month].

    Parameters
    ----------
    config:
        Validated :class:'~samba.scenario.models.ServiceCharge' model.
    load_kw:
        Hourly load [kW], shape (8760,).  Required when
        ''config.type == 'tiered_kwh'''.

    Returns
    -------
    np.ndarray, shape (12,)
        Monthly service charge [$/month].

    Raises
    ------
    ValueError
        If ''load_kw'' is required but not provided.
    """
    if config.type == "flat":
        if config.monthly_flat is None:
            raise ValueError("ServiceCharge.type='flat' requires monthly_flat to be set.")
        return np.full(12, config.monthly_flat, dtype=np.float64)

    if config.type == "tiered_kwh":
        if config.tiers is None:
            raise ValueError("ServiceCharge.type='tiered_kwh' requires tiers to be set.")
        if load_kw is None:
            raise ValueError("load_kw must be provided when service_charge.type='tiered_kwh'.")
        return _calc_tiered_kwh(config.tiers, load_kw)

    raise ValueError(f"Unknown service_charge.type: {config.type!r}")


def _calc_tiered_kwh(tiers: list[TierLevel], load_kw: np.ndarray) -> np.ndarray:
    """Compute monthly service charge based on monthly kWh consumption tiers."""
    result = np.empty(12, dtype=np.float64)
    h = 0
    for m, days in enumerate(_DAYS_IN_MONTH):
        hours = 24 * days
        monthly_kwh = float(np.sum(load_kw[h : h + hours]))
        rate = tiers[-1].rate_per_kwh
        for tier in tiers:
            if tier.limit_kwh is None or monthly_kwh < tier.limit_kwh:
                rate = tier.rate_per_kwh
                break
        result[m] = rate
        h += hours
    return result
