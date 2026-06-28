# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Tariff resolver: dispatch a :class:'~samba.scenario.models.Tariff' to the
appropriate calculator and return the three time-series arrays needed by the
compiler.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from samba.scenario.models import BuyRate, SellRate, Tariff
from samba.tariff.flat import calc_flat_rate
from samba.tariff.monthly import calc_monthly_rate
from samba.tariff.monthly_tiered import calc_monthly_tiered_rate
from samba.tariff.seasonal import calc_seasonal_rate
from samba.tariff.seasonal_tiered import calc_seasonal_tiered_rate
from samba.tariff.service_charge import calc_service_charge
from samba.tariff.tiered import calc_tiered_rate
from samba.tariff.tou import calc_tou_rate
from samba.tariff.ultra_low_tou import calc_ultra_low_tou_rate


@dataclass
class TariffArrays:
    """Time-series arrays produced by the tariff resolver.

    Attributes
    ----------
    cbuy:
        Hourly electricity purchase price [$/kWh], shape (8760,).
    csell:
        Hourly electricity export / sell price [$/kWh], shape (8760,).
        All zeros when no sell rate is defined.
    service_charge:
        Monthly fixed service / standing charge [$/month], shape (12,).
        All zeros when no service charge is defined.
    """

    cbuy: np.ndarray  # (8760,) $/kWh
    csell: np.ndarray  # (8760,) $/kWh
    service_charge: np.ndarray  # (12,)  $/month


def _resolve_buy(rate: BuyRate, load_kw: np.ndarray, year: int) -> np.ndarray:
    t = rate.type
    if t == "flat":
        if rate.rate_per_kwh is None:
            raise ValueError("BuyRate.type='flat' requires rate_per_kwh to be set.")
        return calc_flat_rate(rate.rate_per_kwh)
    if t == "tou":
        if rate.tou_schedule is None:
            raise ValueError("BuyRate.type='tou' requires tou_schedule to be set.")
        return calc_tou_rate(rate.tou_schedule, year=year)
    if t == "ul_tou":
        if rate.tou_schedule is None:
            raise ValueError("BuyRate.type='ul_tou' requires tou_schedule to be set.")
        return calc_ultra_low_tou_rate(rate.tou_schedule, year=year)
    if t == "tiered":
        if rate.tiers is None:
            raise ValueError("BuyRate.type='tiered' requires tiers to be set.")
        return calc_tiered_rate(rate.tiers, load_kw)
    if t == "seasonal":
        if rate.seasonal_schedule is None:
            raise ValueError("BuyRate.type='seasonal' requires seasonal_schedule to be set.")
        return calc_seasonal_rate(rate.seasonal_schedule)
    if t == "seasonal_tiered":
        if rate.seasonal_tiers is None:
            raise ValueError("BuyRate.type='seasonal_tiered' requires seasonal_tiers to be set.")
        return calc_seasonal_tiered_rate(rate.seasonal_tiers, load_kw)
    if t == "monthly":
        if rate.monthly_rates is None:
            raise ValueError("BuyRate.type='monthly' requires monthly_rates to be set.")
        return calc_monthly_rate(rate.monthly_rates)
    if t == "monthly_tiered":
        if rate.monthly_tiers is None:
            raise ValueError("BuyRate.type='monthly_tiered' requires monthly_tiers to be set.")
        return calc_monthly_tiered_rate(rate.monthly_tiers, load_kw)
    raise ValueError(f"Unknown buy rate type: {t!r}")  # pragma: no cover


def _resolve_sell(rate: SellRate | None, load_kw: np.ndarray, year: int) -> np.ndarray:
    if rate is None:
        return np.zeros(8760, dtype=np.float64)
    t = rate.type
    if t == "flat":
        if rate.rate_per_kwh is None:
            raise ValueError("SellRate.type='flat' requires rate_per_kwh to be set.")
        return calc_flat_rate(rate.rate_per_kwh)
    if t == "tou":
        if rate.tou_schedule is None:
            raise ValueError("SellRate.type='tou' requires tou_schedule to be set.")
        return calc_tou_rate(rate.tou_schedule, year=year)
    if t == "monthly":
        if rate.monthly_rates is None:
            raise ValueError("SellRate.type='monthly' requires monthly_rates to be set.")
        return calc_monthly_rate(rate.monthly_rates)
    raise ValueError(f"Unknown sell rate type: {t!r}")  # pragma: no cover


def resolve_tariff(
    tariff: Tariff,
    load_kw: np.ndarray,
    year: int = 2025,
) -> TariffArrays:
    """Resolve a :class:'~samba.scenario.models.Tariff' into three numpy arrays.

    Parameters
    ----------
    tariff:
        Validated tariff model from the scenario.
    load_kw:
        Hourly load profile [kW], shape (8760,).  Required by tiered and
        demand-based rate types.
    year:
        Calendar year for weekday/weekend determination in TOU rates.

    Returns
    -------
    TariffArrays
        ''cbuy'' (8760,), ''csell'' (8760,), ''service_charge'' (12,) arrays.
    """
    cbuy = _resolve_buy(tariff.buy, load_kw, year)
    csell = _resolve_sell(tariff.sell, load_kw, year)

    if tariff.service_charge is not None:
        sc = calc_service_charge(tariff.service_charge, load_kw)
    else:
        sc = np.zeros(12, dtype=np.float64)

    return TariffArrays(cbuy=cbuy, csell=csell, service_charge=sc)
