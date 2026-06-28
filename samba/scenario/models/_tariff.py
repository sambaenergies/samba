# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Electricity tariff schema models.

Defines the leaf TOU/tier/seasonal structures and the top-level
''BuyRate'', ''SellRate'', ''ServiceCharge'', and ''Tariff'' containers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

__all__ = [
    "TouPeriod",
    "TierLevel",
    "SeasonalRate",
    "SeasonalTiers",
    "BuyRate",
    "SellRate",
    "ServiceCharge",
    "DemandCharge",
    "NEM",
    "Tariff",
]


# ---------------------------------------------------------------------------
# Shared leaf models
# ---------------------------------------------------------------------------


class TouPeriod(BaseModel):
    """A single time-of-use pricing period."""

    model_config = ConfigDict(extra="forbid")

    name: str
    months: list[int] = list(range(1, 13))  # 1-12; default all months
    weekday: bool = True
    weekend: bool = True
    hours: list[int]  # 0-23 required
    rate_per_kwh: float

    @field_validator("months")
    @classmethod
    def _validate_months(cls, v: list[int]) -> list[int]:
        if not v or not all(1 <= m <= 12 for m in v):
            raise ValueError("months must be a non-empty list of integers in [1, 12]")
        return v

    @field_validator("hours")
    @classmethod
    def _validate_hours(cls, v: list[int]) -> list[int]:
        if not v or not all(0 <= h <= 23 for h in v):
            raise ValueError("hours must be a non-empty list of integers in [0, 23]")
        return v


class TierLevel(BaseModel):
    """A single consumption tier (for tiered electricity rates)."""

    model_config = ConfigDict(extra="forbid")

    limit_kwh: float | None = None  # None = unlimited (final / top tier)
    rate_per_kwh: float


class SeasonalRate(BaseModel):
    """A flat rate that applies during a specific set of months (season)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    months: list[int]  # 1-12
    rate_per_kwh: float

    @field_validator("months")
    @classmethod
    def _validate_months(cls, v: list[int]) -> list[int]:
        if not v or not all(1 <= m <= 12 for m in v):
            raise ValueError("months must be a non-empty list of integers in [1, 12]")
        return v


class SeasonalTiers(BaseModel):
    """A tiered rate that applies during a specific set of months (season)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    months: list[int]  # 1-12
    tiers: list[TierLevel]

    @field_validator("months")
    @classmethod
    def _validate_months(cls, v: list[int]) -> list[int]:
        if not v or not all(1 <= m <= 12 for m in v):
            raise ValueError("months must be a non-empty list of integers in [1, 12]")
        return v


# ---------------------------------------------------------------------------
# BuyRate
# ---------------------------------------------------------------------------


class BuyRate(BaseModel):
    """Electricity purchase rate from the grid (or notional off-grid price signal)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "flat",
        "tou",
        "tiered",
        "seasonal",
        "seasonal_tiered",
        "monthly",
        "monthly_tiered",
        "ul_tou",
    ]
    rate_per_kwh: float | None = None  # flat
    tou_schedule: list[TouPeriod] | None = None  # tou, ul_tou
    tiers: list[TierLevel] | None = None  # tiered
    seasonal_schedule: list[SeasonalRate] | None = None  # seasonal
    seasonal_tiers: list[SeasonalTiers] | None = None  # seasonal_tiered
    monthly_rates: list[float] | None = None  # monthly (12 values)
    monthly_tiers: list[list[TierLevel]] | None = None  # monthly_tiered (12 lists)
    endogenous_tiering: bool = False  # v2 LP-endogenous tiered cost model

    @model_validator(mode="after")
    def _check_type_fields(self) -> BuyRate:
        t = self.type
        if t == "flat":
            if self.rate_per_kwh is None:
                raise ValueError("rate_per_kwh is required when buy.type='flat'")
        elif t in ("tou", "ul_tou"):
            if not self.tou_schedule:
                raise ValueError(f"tou_schedule is required when buy.type='{t}'")
        elif t == "tiered":
            if not self.tiers:
                raise ValueError("tiers is required when buy.type='tiered'")
        elif t == "seasonal":
            if not self.seasonal_schedule:
                raise ValueError("seasonal_schedule is required when buy.type='seasonal'")
        elif t == "seasonal_tiered":
            if not self.seasonal_tiers:
                raise ValueError("seasonal_tiers is required when buy.type='seasonal_tiered'")
        elif t == "monthly":
            if self.monthly_rates is None or len(self.monthly_rates) != 12:
                raise ValueError(
                    "monthly_rates must be a list of exactly 12 values when buy.type='monthly'"
                )
        elif t == "monthly_tiered" and (
            self.monthly_tiers is None or len(self.monthly_tiers) != 12
        ):
            raise ValueError(
                "monthly_tiers must be a list of exactly 12 tier lists "
                "when buy.type='monthly_tiered'"
            )
        if self.endogenous_tiering and t not in ("tiered", "seasonal_tiered", "monthly_tiered"):
            raise ValueError(
                "endogenous_tiering only applicable to tiered tariff types "
                f"(tiered, seasonal_tiered, monthly_tiered); got type={t!r}"
            )
        return self


# ---------------------------------------------------------------------------
# SellRate
# ---------------------------------------------------------------------------


class SellRate(BaseModel):
    """Electricity export / sell rate to the grid (feed-in tariff)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["flat", "tou", "monthly"]
    rate_per_kwh: float | None = None  # flat
    tou_schedule: list[TouPeriod] | None = None  # tou
    monthly_rates: list[float] | None = None  # monthly (12 values)

    @model_validator(mode="after")
    def _check_type_fields(self) -> SellRate:
        if self.type == "flat" and self.rate_per_kwh is None:
            raise ValueError("rate_per_kwh is required when sell.type='flat'")
        if self.type == "tou" and not self.tou_schedule:
            raise ValueError("tou_schedule is required when sell.type='tou'")
        if self.type == "monthly" and (self.monthly_rates is None or len(self.monthly_rates) != 12):
            raise ValueError(
                "monthly_rates must be a list of exactly 12 values when sell.type='monthly'"
            )
        return self


# ---------------------------------------------------------------------------
# ServiceCharge
# ---------------------------------------------------------------------------


class ServiceCharge(BaseModel):
    """Fixed monthly service / standing charge.

    Note: demand-based service charges ($/kW of monthly peak) are out of scope for v1-v2
    and are deferred to v3+.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["flat", "tiered_kwh"]
    monthly_flat: float | None = None  # $/month; required when type="flat"
    tiers: list[TierLevel] | None = None  # kWh thresholds; required when type="tiered_kwh"

    @model_validator(mode="after")
    def _check_type_fields(self) -> ServiceCharge:
        if self.type == "flat" and self.monthly_flat is None:
            raise ValueError("monthly_flat is required when service_charge.type='flat'")
        if self.type == "tiered_kwh" and not self.tiers:
            raise ValueError("tiers is required when service_charge.type='tiered_kwh'")
        return self


# ---------------------------------------------------------------------------
# Demand charge (v4)
# ---------------------------------------------------------------------------


class DemandCharge(BaseModel):
    """Demand charge on the monthly peak grid import [$/kW-month].

    The charge is applied to the highest grid-import power reached in each
    calendar month (optionally restricted to ``hours``).  It is modelled inside
    the LP as a per-month peak variable, so the solver has an incentive to shave
    peaks (e.g. by discharging storage) rather than merely being billed for them.
    """

    model_config = ConfigDict(extra="forbid")

    rate_per_kw_month: float  # $/kW of monthly peak grid import
    # restrict the peak window to these hours-of-day (0-23); None = all hours
    hours: list[int] | None = None

    @field_validator("rate_per_kw_month")
    @classmethod
    def _validate_rate(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("demand_charge.rate_per_kw_month must be >= 0")
        return v

    @field_validator("hours")
    @classmethod
    def _validate_hours(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and (not v or any(h < 0 or h > 23 for h in v)):
            raise ValueError("demand_charge.hours must be a non-empty subset of 0-23")
        return v


# ---------------------------------------------------------------------------
# Net-metering / net-billing reconciliation (v4)
# ---------------------------------------------------------------------------


class NEM(BaseModel):
    """Annual net-metering / net-billing credit reconciliation.

    Without this, SAMBA nets grid cost annually as ``bought$ − sold$``, letting
    unlimited export revenue offset import cost. Real NEM tariffs instead bill
    **per calendar month** with a **$0 floor**, roll surplus export credit forward,
    and settle whatever credit remains at year end. This model captures those
    three behaviours (all monetary; the export valuation is whatever the user puts
    in the ``sell`` rate, so ``mode`` is intent/labelling):

    - ``net_metering``: exports typically credited at (near) retail — set ``sell``
      equal to the buy rate.
    - ``net_billing``: exports valued at a lower export rate — set ``sell`` accordingly.

    Reconciliation each month: ``net$ = bought$ − sold$``; apply any carried
    credit; the monthly bill is floored at $0; surplus becomes credit (carried
    forward if ``carryover``). At year end, leftover credit is paid back to the
    customer scaled by ``annual_excess_credit_fraction`` (0 = forfeited, the common
    default; 1 = full cash-out).
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["net_metering", "net_billing"] = "net_metering"
    carryover: bool = True  # roll monthly export credit forward to later months
    annual_excess_credit_fraction: float = 0.0  # 0..1; share of leftover year-end credit paid out

    @field_validator("annual_excess_credit_fraction")
    @classmethod
    def _validate_fraction(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("nem.annual_excess_credit_fraction must be in [0, 1]")
        return v


# ---------------------------------------------------------------------------
# Tariff
# ---------------------------------------------------------------------------


class Tariff(BaseModel):
    """Electricity tariff definition."""

    model_config = ConfigDict(extra="forbid")

    buy: BuyRate
    sell: SellRate | None = None  # required when grid.export_allowed; checked at Scenario level
    service_charge: ServiceCharge | None = None
    demand_charge: DemandCharge | None = None  # v4: $/kW-month on monthly peak import
    nem: NEM | None = None  # v4: annual net-metering/billing reconciliation
