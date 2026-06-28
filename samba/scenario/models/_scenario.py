# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Top-level scenario schema models.

Defines Project, Location, Weather, Load, Constraints, Objective, and the
root ''Scenario'' model.  Imports ''Components'' and ''Tariff'' from their
respective sub-modules.
"""

from __future__ import annotations

import zoneinfo
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from samba.scenario.models._components import Components
from samba.scenario.models._tariff import Tariff

__all__ = [
    "Project",
    "Location",
    "Weather",
    "ThermalLoad",
    "Load",
    "Constraints",
    "Objective",
    "Scenario",
]

# ---------------------------------------------------------------------------
# Load source constants (used in Load.source validator)
# ---------------------------------------------------------------------------

_LOAD_CSV_SOURCES = {
    "hourly_csv",
    "daily_csv",
    "monthly_hourly_average",
    "annual_hourly_average",
    "annual_daily_average",
}


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


class Project(BaseModel):
    """Top-level project / economic parameters."""

    model_config = ConfigDict(extra="forbid")

    name: str
    year: int = 2025  # calendar year of simulation (for tariff escalation)
    lifetime_years: int = 25  # 1-40
    discount_rate_nominal: float  # 0.0-1.0; nominal (not real)
    inflation_rate: float = 0.0  # 0.0-1.0
    re_incentive_rate: float = 0.0  # e.g. 0.30 for 30 % ITC; applied to PV+battery capex
    budget: float | None = None  # hard capital-budget limit; same currency as costs
    currency: str = "USD"  # display label only
    capex_year: int = 0  # year of initial investment
    # annual rate at which grid electricity prices escalate
    # (e.g. 0.02 = 2 %/yr); 0 = no escalation
    grid_escalation_rate: float = 0.0

    @model_validator(mode="after")
    def _check_rates(self) -> Project:
        if not (0.0 <= self.discount_rate_nominal <= 1.0):
            raise ValueError("discount_rate_nominal must be in [0, 1]")
        if not (0.0 <= self.inflation_rate <= 1.0):
            raise ValueError("inflation_rate must be in [0, 1]")
        if not (0.0 <= self.re_incentive_rate < 1.0):
            raise ValueError("re_incentive_rate must be in [0, 1)")
        if self.budget is not None and self.budget <= 0.0:
            raise ValueError("budget must be > 0 when specified")
        if self.lifetime_years < 1 or self.lifetime_years > 40:
            raise ValueError("lifetime_years must be in [1, 40]")
        return self


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------


class Location(BaseModel):
    """Geographic location of the site."""

    model_config = ConfigDict(extra="forbid")

    latitude: float  # -90 to 90
    longitude: float  # -180 to 180
    altitude_m: float = 0.0
    timezone: str  # IANA timezone string, e.g. "Africa/Nairobi"

    @field_validator("latitude")
    @classmethod
    def _lat(cls, v: float) -> float:
        if not (-90 <= v <= 90):
            raise ValueError("latitude must be in [-90, 90]")
        return v

    @field_validator("longitude")
    @classmethod
    def _lon(cls, v: float) -> float:
        if not (-180 <= v <= 180):
            raise ValueError("longitude must be in [-180, 180]")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            zoneinfo.ZoneInfo(v)
        except (zoneinfo.ZoneInfoNotFoundError, KeyError) as exc:
            raise ValueError(f"Unknown timezone: {v!r}") from exc
        return v


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------


class Weather(BaseModel):
    """Weather data source configuration.

    - ``"csv"``: load a local NSRDB-format CSV (``csv_path``).
    - ``"nsrdb"`` (v4): fetch a year of NSRDB data from the NREL API for the
      scenario ``location`` and ``project.year``, cached locally so runs are
      reproducible and offline-repeatable. Requires ``nsrdb_api_key`` (or the
      ``NREL_API_KEY`` environment variable).
    """

    model_config = ConfigDict(extra="forbid")

    source: Literal["csv", "nsrdb"]
    csv_path: str | None = None  # required when source="csv"
    nsrdb_api_key: str | None = None  # NREL API key; falls back to $NREL_API_KEY
    nsrdb_email: str | None = None  # required by the NREL API; falls back to $NREL_API_EMAIL

    @model_validator(mode="after")
    def _check_source_fields(self) -> Weather:
        if self.source == "csv" and self.csv_path is None:
            raise ValueError("csv_path is required when weather.source='csv'")
        return self


# ---------------------------------------------------------------------------
# Thermal load (Phase 22 -- full schema)
# ---------------------------------------------------------------------------


class ThermalLoad(BaseModel):
    """Thermal load profile configuration.

    Supports two loading strategies:

    * ``"csv"`` -- supply hourly kW_th arrays directly as CSV files.
    * ``"degree_day"`` -- derive heating/cooling demand from outdoor temperature
      using a per-degree heat-loss model parameterised by ``building_ua_kw_per_k``.

    Distribution efficiency
    -----------------------
    ``distribution_efficiency`` accounts for losses in the pipe/duct system
    between the heat pump (or boiler) output and the point of demand.  The
    thermal demand seen by the supply component equals
    ``raw_demand / distribution_efficiency``.

    Thermal LPSP
    -----------
    When ``scenario.constraints.thermal_lpsp_max > 0`` the optimizer is
    allowed to leave a fraction of thermal demand unmet (deficit drawn from
    the ``heat_unmet`` / ``cool_unmet`` penalty sources).  Use this for
    load-shedding studies.
    """

    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    source: Literal["csv", "degree_day"] = "csv"

    # --- CSV branch ---
    heating_csv_path: str | None = None  # hourly kW_th, 8760 rows
    cooling_csv_path: str | None = None  # hourly kW_th, 8760 rows

    # --- Degree-day branch ---
    building_ua_kw_per_k: float | None = None  # UA coefficient [kW/K]
    building_ua_cool_kw_per_k: float | None = None  # overrides ua for cooling; defaults to ua
    heating_setpoint_c: float = 20.0  # indoor heating setpoint [\u00b0C]
    cooling_setpoint_c: float = 24.0  # indoor cooling setpoint [\u00b0C]

    # --- Distribution ---
    distribution_efficiency: float = 0.95  # 0 < \u03b7 \u2264 1

    @model_validator(mode="after")
    def _check_thermal_load_fields(self) -> ThermalLoad:
        if self.source == "csv":
            if self.heating_csv_path is None and self.cooling_csv_path is None:
                raise ValueError(
                    "ThermalLoad.source='csv' requires at least one of "
                    "heating_csv_path or cooling_csv_path."
                )
        elif self.source == "degree_day" and self.building_ua_kw_per_k is None:
            raise ValueError("ThermalLoad.source='degree_day' requires building_ua_kw_per_k.")
        if self.heating_setpoint_c >= self.cooling_setpoint_c:
            raise ValueError(
                "heating_setpoint_c must be less than cooling_setpoint_c; "
                f"got {self.heating_setpoint_c} >= {self.cooling_setpoint_c}."
            )
        if not (0.0 < self.distribution_efficiency <= 1.0):
            raise ValueError(
                f"distribution_efficiency must be in (0, 1]; got {self.distribution_efficiency}."
            )
        return self


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


class Load(BaseModel):
    """Electrical load profile configuration."""

    model_config = ConfigDict(extra="forbid")

    source: Literal[
        "hourly_csv",  # 8 760-row CSV, one kW value per hour
        "daily_csv",  # 24-row CSV; repeated for all 365 days
        "monthly_total",  # 12 monthly kWh totals; expanded via daily distribution
        "monthly_hourly_average",  # 12x24 matrix CSV; expanded to 8 760 h
        "annual_hourly_average",  # 8 760-row annual average profile; scaled to annual total
        "annual_daily_average",  # 24-row daily average; repeated to 8 760 h
        "generic_monthly",  # monthly peak (kW) drives generic_load algorithm
        "generic_annual",  # annual kWh + monthly_peak list drives generic_load
        "generic_annual_total",  # single annual kWh total; generic_load flat profile
        "generic",  # fully parameterised generic_load call
        "template",  # built-in residential/commercial/industrial shape scaled to annual_kwh
    ]
    csv_path: str | None = None
    template_name: str | None = None  # required when source='template'
    daily_profile: list[float] | None = None  # 24 hourly kWh values
    monthly_peak: list[float] | None = None  # 12 monthly peak kW values
    scale_factor: float = 1.0
    annual_kwh: float | None = (
        None  # target annual energy [kWh]; used when source='generic_annual_total'
    )
    peak_month: str = (
        "January"  # peak demand month for generic load profiles (e.g. 'July' for summer climates)
    )
    # Thermal load configuration (Phase 19+)
    thermal: ThermalLoad | None = None

    @field_validator("daily_profile")
    @classmethod
    def _daily_len(cls, v: list[float] | None) -> list[float] | None:
        if v is not None and len(v) != 24:
            raise ValueError(f"daily_profile must have exactly 24 elements, got {len(v)}")
        return v

    @field_validator("monthly_peak")
    @classmethod
    def _monthly_len(cls, v: list[float] | None) -> list[float] | None:
        if v is not None and len(v) != 12:
            raise ValueError(f"monthly_peak must have exactly 12 elements, got {len(v)}")
        return v

    @model_validator(mode="after")
    def _check_source_fields(self) -> Load:
        if self.source in _LOAD_CSV_SOURCES and self.csv_path is None:
            raise ValueError(f"csv_path is required when load.source='{self.source}'")
        if self.source == "generic_annual_total" and self.annual_kwh is None:
            raise ValueError("annual_kwh is required when load.source='generic_annual_total'")
        return self


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


class Constraints(BaseModel):
    """Hard optimisation constraints.

    Every field here is a **hard** model constraint, not a KPI-only warning.
    Violations cause the solver to reject candidate solutions outright.
    """

    model_config = ConfigDict(extra="forbid")

    min_renewable_fraction: float = 0.0  # 0-1; minimum share of load met by renewables
    max_annual_diesel_l: float | None = None  # absolute annual diesel consumption ceiling (L)
    max_battery_cycles_yr: float | None = None  # maximum annual equivalent full cycles
    max_lpsp: float = 0.0  # Loss of Power Supply Probability (0-1); 0 = no unmet demand
    force_grid_disconnect: bool = False  # simulate off-grid even when grid component present
    thermal_lpsp_max: float = 0.0  # max fraction of thermal demand that may go unmet [0, 1]
    max_total_emissions_kg: float | None = None  # v4: hard cap on annual CO2 (epsilon-constraint)

    @model_validator(mode="after")
    def _validate_constraints(self) -> Constraints:
        if not (0.0 <= self.min_renewable_fraction <= 1.0):
            raise ValueError("constraints.min_renewable_fraction must be in [0, 1]")
        if not (0.0 <= self.max_lpsp <= 1.0):
            raise ValueError("constraints.max_lpsp must be in [0, 1]")
        if not (0.0 <= self.thermal_lpsp_max <= 1.0):
            raise ValueError("constraints.thermal_lpsp_max must be in [0, 1]")
        return self


# ---------------------------------------------------------------------------
# Objective
# ---------------------------------------------------------------------------


class Objective(BaseModel):
    """Optimisation objective.

    type ''"cost"'' minimises NPC only (default, v1 behaviour).
    type ''"cost_and_emissions"'' adds a carbon price (''emissions_weight'' $/kg CO2)
    to both the diesel and grid import variable costs inside the LP objective, so the
    solver trades off cost against emissions.  Use ''samba pareto'' to sweep over
    ''emissions_weight'' values and generate a weighted-sum approximation of the
    Pareto front.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["cost", "cost_and_emissions"] = "cost"
    emissions_weight: float = 0.0  # $/kg CO2; only used when type='cost_and_emissions'

    @field_validator("emissions_weight")
    @classmethod
    def _ew(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError("objective.emissions_weight must be >= 0")
        return v


# ---------------------------------------------------------------------------
# Top-level Scenario
# ---------------------------------------------------------------------------


class Scenario(BaseModel):
    """Root model for a SAMBA scenario file."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.1"  # 1.0 also accepted (backward compatible)
    project: Project
    location: Location
    weather: Weather
    load: Load
    components: Components
    tariff: Tariff
    constraints: Constraints = Constraints()
    objective: Objective = Objective()

    @model_validator(mode="after")
    def _check_sell_rate_required(self) -> Scenario:
        grid = self.components.grid
        if grid is not None and grid.export_allowed and self.tariff.sell is None:
            raise ValueError("tariff.sell is required when components.grid.export_allowed is True")
        return self
