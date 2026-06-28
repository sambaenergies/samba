# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Physical component schema models.

Defines PV, Battery (Li-ion + KiBaM), Wind, Diesel Generator, Inverter,
Grid, EV, and the top-level ''Components'' container.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

__all__ = [
    "PV",
    "KiBaMParams",
    "Battery",
    "WindTurbine",
    "DieselGenerator",
    "Inverter",
    "Grid",
    "EV",
    # Thermal stubs (Phase 19)
    "HeatPump",
    "ThermalStorage",
    # Gas supply (Phase 23)
    "GasSeasonalRate",
    "GasTariff",
    "GasSupply",
    "Components",
]


# ---------------------------------------------------------------------------
# PV
# ---------------------------------------------------------------------------


class PV(BaseModel):
    """Photovoltaic array configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    capacity_kw: float | None = None  # None = Investment (design variable)
    capex_per_kw: float
    opex_per_kw_yr: float = 0.0
    lifetime_years: int = 25
    derating_factor: float = 0.9  # 0-1; accounts for soiling, mismatch, wiring losses
    tilt_deg: float = 20.0  # 0-90 degrees
    azimuth_deg: float = 180.0  # 0-360 degrees
    module_type: Literal["monofacial", "bifacial"] = "monofacial"
    bifaciality: float = 0.7  # rear/front efficiency ratio; only used when module_type='bifacial'
    noct_celsius: float = 45.0  # Nominal Operating Cell Temperature
    temp_coeff_pmax: float = -0.004  # per degC; typically negative

    @model_validator(mode="after")
    def _validate_pv(self) -> PV:
        if self.capacity_kw is not None and self.capacity_kw <= 0:
            raise ValueError("pv.capacity_kw must be > 0 when specified")
        if not (0.0 < self.derating_factor <= 1.0):
            raise ValueError("pv.derating_factor must be in (0, 1]")
        if not (0.0 <= self.bifaciality <= 1.0):
            raise ValueError("pv.bifaciality must be in [0, 1]")
        return self


# ---------------------------------------------------------------------------
# Battery (Li-ion + KiBaM)
# ---------------------------------------------------------------------------


class KiBaMParams(BaseModel):
    """Lead-acid KiBaM kinetic parameters (used when battery.chemistry == 'kibam')."""

    model_config = ConfigDict(extra="forbid")

    c_ratio: float = 0.42  # available-to-total capacity ratio
    k_rate: float = 0.58  # rate constant [h-1]
    charge_acceptance: float = 0.9  # alfa_battery_leadacid -- acceptance rate coefficient
    max_charge_current_a: float = 100.0  # Ich_max_leadacid [A]
    nominal_voltage_v: float = 12.0  # Vnom_leadacid [V]

    @field_validator("c_ratio")
    @classmethod
    def _val_c_ratio(cls, v: float) -> float:
        if not (0.0 < v < 1.0):
            raise ValueError(f"kibam.c_ratio must be in (0, 1), got {v}")
        return v

    @field_validator("k_rate")
    @classmethod
    def _val_k_rate(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError(f"kibam.k_rate must be > 0, got {v}")
        return v


class BatteryDegradation(BaseModel):
    """Capacity-fade model that derives the battery's replacement cadence (v4).

    When set, the battery's *effective* lifetime is computed from a linear fade
    model (calendar + cycling) rather than the fixed ``lifetime_years`` nameplate:
    annual fade [%] = ``calendar_fade_pct_yr`` + ``cycle_fade_pct_per_efc`` x
    (annual equivalent full cycles), and the battery is replaced when cumulative
    fade reaches ``end_of_life_capacity_pct``. EFC is derived from the solved
    annual discharge throughput, so heavier cycling shortens life.
    """

    model_config = ConfigDict(extra="forbid")

    calendar_fade_pct_yr: float = 0.0  # %/yr capacity loss from calendar ageing
    cycle_fade_pct_per_efc: float = 0.0  # % capacity loss per equivalent full cycle
    end_of_life_capacity_pct: float = 80.0  # replace when capacity falls below this % of nameplate

    @field_validator("calendar_fade_pct_yr", "cycle_fade_pct_per_efc")
    @classmethod
    def _val_fade(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("battery degradation fade rates must be >= 0")
        return v

    @field_validator("end_of_life_capacity_pct")
    @classmethod
    def _val_eol(cls, v: float) -> float:
        if not (0.0 < v < 100.0):
            raise ValueError("battery degradation end_of_life_capacity_pct must be in (0, 100)")
        return v


class Battery(BaseModel):
    """Battery energy storage configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    capacity_kwh: float | None = None  # None = Investment (design variable)
    power_kw: float | None = None  # None = derived from capacity at runtime
    chemistry: Literal["li_ion", "kibam"] = "li_ion"
    kibam: KiBaMParams | None = None  # required (and auto-populated) when chemistry="kibam"
    degradation: BatteryDegradation | None = None  # v4: capacity-fade replacement model
    capex_per_kwh: float
    opex_per_kwh_yr: float = 0.0
    lifetime_years: int = 10
    soc_min: float = 0.2  # 0-1
    soc_max: float = 1.0  # 0-1
    soc_initial: float = 0.5  # 0-1
    charge_efficiency: float = 0.95  # 0-1
    discharge_efficiency: float = 0.95  # 0-1
    c_rate_charge: float = 0.5  # fraction of capacity per hour
    c_rate_discharge: float = 0.5  # fraction of capacity per hour

    @model_validator(mode="after")
    def _validate_battery(self) -> Battery:
        soc_fields = {
            "soc_min": self.soc_min,
            "soc_max": self.soc_max,
            "soc_initial": self.soc_initial,
        }
        for name, val in soc_fields.items():
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"battery.{name} must be in [0, 1], got {val}")
        if self.soc_min >= self.soc_max:
            raise ValueError(f"battery.soc_min ({self.soc_min}) must be < soc_max ({self.soc_max})")
        for name, val in [
            ("charge_efficiency", self.charge_efficiency),
            ("discharge_efficiency", self.discharge_efficiency),
        ]:
            if not (0.0 < val <= 1.0):
                raise ValueError(f"battery.{name} must be in (0, 1], got {val}")
        if self.c_rate_charge <= 0:
            raise ValueError("battery.c_rate_charge must be > 0")
        if self.c_rate_discharge <= 0:
            raise ValueError("battery.c_rate_discharge must be > 0")
        # KiBaM: auto-populate kibam params with defaults if not provided
        if self.chemistry == "kibam" and self.kibam is None:
            object.__setattr__(self, "kibam", KiBaMParams())
        return self


# ---------------------------------------------------------------------------
# Wind
# ---------------------------------------------------------------------------


class WindTurbine(BaseModel):
    """Wind turbine configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    count: int = 1  # fixed unit count in v1
    turbine_model: str  # looked up in internal power-curve table
    hub_height_m: float = 50.0
    capex_per_unit: float
    opex_per_unit_yr: float = 0.0
    lifetime_years: int = 20


# ---------------------------------------------------------------------------
# DieselGenerator
# ---------------------------------------------------------------------------


class DieselGenerator(BaseModel):
    """Diesel generator configuration.  Capacity is always fixed in v1."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    capacity_kw: float  # fixed; not a design variable in v1
    capex_per_kw: float
    opex_per_kw_yr: float = 0.0
    lifetime_years: int = 15
    fuel_price_per_l: float
    fuel_lhv_kwh_per_l: float = 9.9  # Lower Heating Value of diesel
    slope_l_per_kwh: float = 0.246  # fuel-curve slope
    intercept_l_per_kw_hr: float = 0.084  # fuel-curve intercept (fraction of rated capacity)
    min_load_fraction: float = 0.0  # 0-1; minimum stable generation level
    co2_per_liter_kg: float = 2.63  # CO2-equivalent emission factor (kg per litre)

    # Unit-commitment fields (MILP) -- default 0 means LP-equivalent (inactive)
    min_up_hours: int = 0  # minimum consecutive ON hours once started
    min_down_hours: int = 0  # minimum consecutive OFF hours once stopped
    startup_cost: float = 0.0  # one-time cost per start event [$]

    @field_validator("min_up_hours")
    @classmethod
    def _val_min_up(cls, v: int) -> int:
        if v < 0:
            raise ValueError("diesel_generator.min_up_hours must be >= 0")
        return v

    @field_validator("min_down_hours")
    @classmethod
    def _val_min_down(cls, v: int) -> int:
        if v < 0:
            raise ValueError("diesel_generator.min_down_hours must be >= 0")
        return v

    @field_validator("startup_cost")
    @classmethod
    def _val_startup_cost(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("diesel_generator.startup_cost must be >= 0")
        return v

    @model_validator(mode="after")
    def _val_uc_sanity(self) -> DieselGenerator:
        if self.min_up_hours + self.min_down_hours > 8760:
            raise ValueError("diesel_generator.min_up_hours + min_down_hours must be <= 8760")
        return self


# ---------------------------------------------------------------------------
# Inverter
# ---------------------------------------------------------------------------


class Inverter(BaseModel):
    """AC/DC inverter configuration."""

    model_config = ConfigDict(extra="forbid")

    capacity_kw: float | None = None  # None = Investment (design variable)
    capex_per_kw: float
    opex_per_kw_yr: float = 0.0
    lifetime_years: int = 10
    efficiency: float = 0.96  # 0-1

    @field_validator("efficiency")
    @classmethod
    def _eff(cls, v: float) -> float:
        if not (0.0 < v <= 1.0):
            raise ValueError("inverter.efficiency must be in (0, 1]")
        return v


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------


class Grid(BaseModel):
    """Grid connection configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    capacity_kw: float  # import power limit
    export_allowed: bool = False
    export_capacity_kw: float = 0.0  # export power limit; relevant only if export_allowed
    capex: float = 0.0  # connection / infrastructure cost
    opex_yr: float = 0.0  # annual grid connection fee
    emission_factor_kg_per_kwh: float = (
        0.0  # grid CO2 intensity (kg per kWh imported); 0 = no grid emissions
    )

    @field_validator("emission_factor_kg_per_kwh")
    @classmethod
    def _grid_ef(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("grid.emission_factor_kg_per_kwh must be >= 0")
        return v


# ---------------------------------------------------------------------------
# EV / V2G
# ---------------------------------------------------------------------------


class EV(BaseModel):
    """Electric vehicle smart-charging / V2G component.

    The EV battery is modeled as a :class:'solph.components.GenericStorage' on
    the AC bus with time-varying charge/discharge bounds derived from a
    presence schedule.  V2G discharge earns sell-tariff revenue when enabled.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True

    # Physical battery
    capacity_kwh: float  # usable battery capacity
    max_charge_kw: float  # Level 2 or DC fast-charger limit
    max_discharge_kw: float = 0.0  # V2G rated power; 0 = no V2G
    soc_min: float = 0.1
    soc_max: float = 1.0
    soc_initial: float = 0.5
    soc_departure: float = 0.8  # required SOC at each departure
    soc_arrival: float = 0.3  # assumed SOC on each return (after travel)
    charge_efficiency: float = 0.92
    discharge_efficiency: float = 0.92  # V2G discharge round-trip efficiency
    self_discharge_rate: float = 0.0  # per hour; 0 = ideal
    v2g_enabled: bool = False

    # Presence schedule
    presence_source: Literal["schedule", "csv"] = "schedule"
    arrival_hour: int = 18  # 0-23 local time; EV returns home
    departure_hour: int = 8  # 0-23 local time; EV leaves home
    workdays_per_week: int = 5  # 1-7; EV commutes on these many weekdays
    presence_csv_path: str | None = None  # required if presence_source="csv"

    # Economics (charger hardware, not vehicle cost)
    capex: float = 0.0  # [$] smart-charger hardware capital cost
    opex_per_year: float = 0.0  # [$/yr] annual O&M
    lifetime_years: int = 10
    replacement_cost: float = 0.0  # [$/kWh] battery replacement per kWh
    lifetime_kwh: float = 200_000.0  # [kWh] lifetime throughput for wear accounting

    @model_validator(mode="after")
    def _val_soc_bounds(self) -> EV:
        if not (0.0 <= self.soc_min < self.soc_max <= 1.0):
            raise ValueError("ev: soc_min < soc_max required; both in [0, 1]")
        if not (0.0 <= self.soc_initial <= 1.0):
            raise ValueError("ev.soc_initial must be in [0, 1]")
        if not (0.0 <= self.soc_departure <= 1.0):
            raise ValueError("ev.soc_departure must be in [0, 1]")
        if not (0.0 <= self.soc_arrival <= 1.0):
            raise ValueError("ev.soc_arrival must be in [0, 1]")
        if self.soc_departure <= self.soc_arrival:
            raise ValueError("ev.soc_departure must be strictly greater than ev.soc_arrival")
        return self

    @field_validator("arrival_hour", "departure_hour")
    @classmethod
    def _val_hour(cls, v: int) -> int:
        if not (0 <= v <= 23):
            raise ValueError("ev arrival_hour and departure_hour must be in [0, 23]")
        return v

    @model_validator(mode="after")
    def _val_hours_differ(self) -> EV:
        if self.arrival_hour == self.departure_hour:
            raise ValueError("ev.arrival_hour must differ from ev.departure_hour")
        return self

    @field_validator("workdays_per_week")
    @classmethod
    def _val_workdays(cls, v: int) -> int:
        if not (1 <= v <= 7):
            raise ValueError("ev.workdays_per_week must be in [1, 7]")
        return v

    @model_validator(mode="after")
    def _val_v2g(self) -> EV:
        if self.v2g_enabled and self.max_discharge_kw <= 0.0:
            raise ValueError("ev.max_discharge_kw must be > 0 when ev.v2g_enabled is True")
        if not self.v2g_enabled and self.max_discharge_kw != 0.0:
            raise ValueError("ev.max_discharge_kw must be 0 when ev.v2g_enabled is False")
        return self

    @model_validator(mode="after")
    def _val_csv_path(self) -> EV:
        if self.presence_source == "csv" and self.presence_csv_path is None:
            raise ValueError("ev.presence_csv_path must be provided when ev.presence_source='csv'")
        return self

    @field_validator("charge_efficiency", "discharge_efficiency")
    @classmethod
    def _val_efficiency(cls, v: float) -> float:
        if not (0.0 < v <= 1.0):
            raise ValueError("ev efficiency values must be in (0, 1]")
        return v

    @field_validator("capacity_kwh", "max_charge_kw")
    @classmethod
    def _val_positive(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("ev capacity_kwh and max_charge_kw must be > 0")
        return v

    @field_validator("self_discharge_rate")
    @classmethod
    def _val_self_discharge(cls, v: float) -> float:
        if not (0.0 <= v < 1.0):
            raise ValueError("ev.self_discharge_rate must be in [0, 1)")
        return v


# ---------------------------------------------------------------------------
# Thermal component stubs (Phase 19 -- full fields added in Phases 20-23)
# ---------------------------------------------------------------------------


class HeatPump(BaseModel):
    """Air-source heat pump (electrically driven, reversible).

    Models the HP as one or two oemof ``Converter`` objects connecting the
    AC bus to the heating / cooling thermal buses.  Hourly COP arrays are
    pre-computed from outdoor temperature using a physics-based
    (Carnot-fraction) model -- see :mod:`samba.thermal.cop`.

    Sizing modes
    ------------
    ``catalog_auto``  --  Automatically select the smallest catalog model
        whose rated capacity meets the peak thermal demand.  Requires thermal
        load peaks to be known (Phase 22).  Defaults to the smallest model
        (18000 BTU/hr) when no thermal load is configured.
    ``fixed``  --  User specifies ``heating_capacity_kw`` /
        ``cooling_capacity_kw`` directly; ``model_name`` is optional.

    COP sources
    -----------
    ``catalog``  --  Physics-based Carnot-fraction COP curve evaluated against
        outdoor temperature (see :mod:`samba.thermal.cop`).
    ``fixed``  --  Constant COP for all timesteps.  Requires
        ``fixed_cop_heating`` (if mode includes heating) and
        ``fixed_cop_cooling`` (if mode includes cooling).
    ``dataset``  --  COP curves fitted from a user-supplied performance dataset
        CSV (``cop_dataset_path``); see :mod:`samba.thermal.cop_dataset`.
    """

    model_config = ConfigDict(extra="forbid")
    enabled: bool = True

    # Operating mode
    mode: Literal["heating_only", "cooling_only", "both"] = "both"

    # Sizing approach
    sizing: Literal["catalog_auto", "fixed"] = "catalog_auto"
    model_name: str | None = None  # e.g. "ASHP-3ton"; if None, auto-selected
    heating_capacity_kw: float | None = None  # used when sizing="fixed"
    cooling_capacity_kw: float | None = None  # used when sizing="fixed"

    # COP source
    cop_source: Literal["catalog", "fixed", "dataset"] = "catalog"
    fixed_cop_heating: float | None = None  # used when cop_source="fixed"
    fixed_cop_cooling: float | None = None  # used when cop_source="fixed"
    cop_dataset_path: str | None = None  # CSV of COP rating points; used when cop_source="dataset"

    # Indoor design conditions (for cooling COP wet-bulb computation)
    indoor_design_temp_c: float = 22.22  # ~72 deg F comfort setpoint [deg C]
    indoor_humidity_ratio: float = 0.005  # kg/kg dry air
    atmospheric_pressure_kpa: float = 101.325  # kPa

    # Stand-by / parasitic load
    standby_power_kw: float = 0.0  # always-on draw (controls, fans) [kW]

    # Economics
    capex: float = 0.0  # $/installed unit (whole system)
    opex_per_year: float = 0.0
    lifetime_years: int = 15

    @model_validator(mode="after")
    def _validate_fixed_cop(self) -> HeatPump:
        if self.cop_source == "fixed":
            if self.mode in ("heating_only", "both") and self.fixed_cop_heating is None:
                raise ValueError(
                    "cop_source='fixed' with mode='heating_only' or 'both' "
                    "requires fixed_cop_heating to be set"
                )
            if self.mode in ("cooling_only", "both") and self.fixed_cop_cooling is None:
                raise ValueError(
                    "cop_source='fixed' with mode='cooling_only' or 'both' "
                    "requires fixed_cop_cooling to be set"
                )
        if self.cop_source == "dataset" and self.cop_dataset_path is None:
            raise ValueError("cop_source='dataset' requires cop_dataset_path to be set")
        return self

    @model_validator(mode="after")
    def _validate_fixed_sizing(self) -> HeatPump:
        if self.sizing == "fixed":
            if self.mode in ("heating_only", "both") and self.heating_capacity_kw is None:
                raise ValueError(
                    "sizing='fixed' with mode='heating_only' or 'both' "
                    "requires heating_capacity_kw to be set"
                )
            if self.mode in ("cooling_only", "both") and self.cooling_capacity_kw is None:
                raise ValueError(
                    "sizing='fixed' with mode='cooling_only' or 'both' "
                    "requires cooling_capacity_kw to be set"
                )
        return self


class ThermalStorage(BaseModel):
    """Hot-water buffer tank or chilled-water thermal storage (Phase 21).

    The storage is modelled as an oemof ``GenericStorage`` on the heating
    (and optionally cooling) thermal bus.  Energy losses are represented by a
    fixed hourly fractional ``loss_rate_per_hour`` rather than temperature-
    dependent physics (phase 21 simplification).

    Default ``loss_rate_per_hour = 0.002`` (0.2 %/h) corresponds roughly to a
    well-insulated 200-L hot-water tank held at 60 °C in a 20 °C room:
    ``Q_loss ≈ (1.5 m²) × (40 K) / (6 m²K/W) / (200 L × 0.00116 kWh/L/K) ≈ 0.2 %/h``.
    """

    model_config = ConfigDict(extra="forbid")
    enabled: bool = True

    # --- Sizing ---
    sizing: Literal["fixed", "investment"] = "investment"
    capacity_kwh_th: float | None = None  # required when sizing="fixed"
    capacity_min_kwh_th: float = 0.0  # investment lower bound [kWh_th]
    capacity_max_kwh_th: float = 200.0  # investment upper bound [kWh_th]

    # --- Operating limits ---
    soc_min: float = 0.0
    soc_max: float = 1.0
    soc_initial: float = 0.5

    # --- Thermal performance ---
    loss_rate_per_hour: float = 0.002  # fraction of stored energy lost / h
    charge_power_max_kw_th: float | None = None  # None → bounded by capacity (1 C)
    discharge_power_max_kw_th: float | None = None

    # --- Cooling-side storage (chilled-water tank on cool_bus) ---
    include_cooling_storage: bool = False
    cooling_capacity_kwh_th: float | None = None  # required when include_cooling=True + fixed
    cooling_capacity_max_kwh_th: float = 100.0  # investment upper bound

    # --- Economics ---
    capex_per_kwh_th: float = 15.0  # $/kWh_th installed
    opex_per_year: float = 0.0
    lifetime_years: int = 20

    @model_validator(mode="after")
    def _validate(self) -> ThermalStorage:
        if self.sizing == "fixed" and self.capacity_kwh_th is None:
            raise ValueError("ThermalStorage: capacity_kwh_th required when sizing='fixed'")
        if (
            self.include_cooling_storage
            and self.sizing == "fixed"
            and self.cooling_capacity_kwh_th is None
        ):
            raise ValueError(
                "ThermalStorage: cooling_capacity_kwh_th required when "
                "include_cooling_storage=True and sizing='fixed'"
            )
        if not (0.0 <= self.soc_min < self.soc_max <= 1.0):
            raise ValueError("ThermalStorage: must have 0 <= soc_min < soc_max <= 1")
        if not (0.0 <= self.loss_rate_per_hour <= 0.1):
            raise ValueError("ThermalStorage: loss_rate_per_hour must be in [0, 0.1]")
        return self


# ---------------------------------------------------------------------------
# Gas supply (Phase 23)
# ---------------------------------------------------------------------------


class GasSeasonalRate(BaseModel):
    """A gas rate band that applies to a fixed set of calendar months."""

    model_config = ConfigDict(extra="forbid")

    months: list[int]  # 1-12 inclusive
    rate: float  # $/unit (same unit as parent GasTariff.unit)

    @field_validator("months")
    @classmethod
    def _validate_months(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("GasSeasonalRate.months must not be empty")
        if any(m < 1 or m > 12 for m in v):
            raise ValueError("GasSeasonalRate.months values must be in 1-12")
        return v

    @field_validator("rate")
    @classmethod
    def _validate_rate(cls, v: float) -> float:
        if v < 0:
            raise ValueError("GasSeasonalRate.rate must be >= 0")
        return v


class GasTariff(BaseModel):
    """Gas tariff structure -- supports flat, seasonal, and tiered pricing."""

    model_config = ConfigDict(extra="forbid")

    rate_type: Literal["flat", "seasonal", "tiered"] = "flat"
    unit: Literal["per_kwh_th", "per_gj", "per_mcf", "per_therm"] = "per_kwh_th"

    flat_rate: float | None = None
    seasonal_schedule: list[GasSeasonalRate] | None = None

    # Tiered: parallel lists of monthly cumulative thresholds and $/unit rates.
    tiered_limits_kwh_th: list[float] | None = None  # monthly upper limits in kWh_th
    tiered_rates: list[float] | None = None  # $/unit per tier (same unit as .unit)

    monthly_service_charge: float = 0.0  # $/month fixed charge
    min_charge_per_month: float = 0.0  # $/month minimum monthly charge

    @model_validator(mode="after")
    def _validate_tariff(self) -> GasTariff:
        if self.rate_type == "flat":
            if self.flat_rate is None:
                raise ValueError("GasTariff: flat_rate is required for rate_type='flat'")
            if self.flat_rate < 0:
                raise ValueError("GasTariff: flat_rate must be >= 0")
        elif self.rate_type == "seasonal":
            if not self.seasonal_schedule:
                raise ValueError(
                    "GasTariff: seasonal_schedule is required for rate_type='seasonal'"
                )
        elif self.rate_type == "tiered":
            if self.tiered_limits_kwh_th is None or self.tiered_rates is None:
                raise ValueError(
                    "GasTariff: tiered_limits_kwh_th and tiered_rates are required "
                    "for rate_type='tiered'"
                )
            if len(self.tiered_limits_kwh_th) != len(self.tiered_rates):
                raise ValueError(
                    "GasTariff: tiered_limits_kwh_th and tiered_rates must have the same length"
                )
            if any(r < 0 for r in self.tiered_rates):
                raise ValueError("GasTariff: all tiered_rates must be >= 0")
        if self.monthly_service_charge < 0:
            raise ValueError("GasTariff: monthly_service_charge must be >= 0")
        if self.min_charge_per_month < 0:
            raise ValueError("GasTariff: min_charge_per_month must be >= 0")
        return self


class GasSupply(BaseModel):
    """Natural gas supply configuration (Phase 23).

    Models a gas-fired boiler as an alternative or supplemental thermal source.
    oemof topology::

        [gas_supply Source] --gas_bus--> [gas_boiler Converter] --heat_bus--> demand
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    boiler_efficiency: float = 0.92  # LHV thermal efficiency, (0, 1]
    max_output_kw_th: float | None = None  # peak thermal output; None = unconstrained
    tariff: GasTariff = GasTariff(rate_type="flat", flat_rate=0.04)
    capex: float = 2000.0  # $/unit total installed cost
    opex_per_year: float = 100.0  # $/year fixed O&M
    lifetime_years: int = 20
    co2_per_kwh_th: float = 0.205  # kg CO2/kWh_th (natural gas combustion, LHV)

    @model_validator(mode="after")
    def _validate_gas_supply(self) -> GasSupply:
        if not (0.0 < self.boiler_efficiency <= 1.0):
            raise ValueError("GasSupply: boiler_efficiency must be in (0, 1]")
        if self.max_output_kw_th is not None and self.max_output_kw_th <= 0:
            raise ValueError("GasSupply: max_output_kw_th must be > 0 when specified")
        if self.capex < 0:
            raise ValueError("GasSupply: capex must be >= 0")
        if self.opex_per_year < 0:
            raise ValueError("GasSupply: opex_per_year must be >= 0")
        if self.lifetime_years <= 0:
            raise ValueError("GasSupply: lifetime_years must be > 0")
        if self.co2_per_kwh_th < 0:
            raise ValueError("GasSupply: co2_per_kwh_th must be >= 0")
        return self


# ---------------------------------------------------------------------------
# Components container
# ---------------------------------------------------------------------------


class Components(BaseModel):
    """Container for all system components."""

    model_config = ConfigDict(extra="forbid")

    pv: PV | None = None
    battery: Battery | None = None
    wind_turbine: WindTurbine | None = None
    diesel_generator: DieselGenerator | None = None
    inverter: Inverter  # always required
    grid: Grid | None = None
    ev: EV | None = None
    # Thermal components (Phases 19-23)
    heat_pump: HeatPump | None = None
    thermal_storage: ThermalStorage | None = None
    gas_supply: GasSupply | None = None

    @model_validator(mode="after")
    def _require_generation_source(self) -> Components:
        has_source = any(
            [
                self.pv is not None,
                self.wind_turbine is not None,
                self.diesel_generator is not None,
                self.grid is not None,
            ]
        )
        if not has_source:
            raise ValueError(
                "At least one generation source must be present: "
                "pv, wind_turbine, diesel_generator, or grid"
            )
        return self

    @model_validator(mode="after")
    def _require_thermal_source_for_storage(self) -> Components:
        """Thermal storage requires at least one thermal source (heat pump or gas)."""
        ts = self.thermal_storage
        if ts is not None and ts.enabled:
            hp_on = self.heat_pump is not None and self.heat_pump.enabled
            gas_on = self.gas_supply is not None and self.gas_supply.enabled
            if not (hp_on or gas_on):
                raise ValueError(
                    "thermal_storage requires at least one thermal source: "
                    "heat_pump or gas_supply must be enabled"
                )
        return self
