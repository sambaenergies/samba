/* eslint-disable */
/**
 * AUTO-GENERATED from ../../../schemas by `npm run gen:types`. DO NOT EDIT.
 * Source of truth: backend Pydantic models (see scripts/export_schemas.py).
 */

export type CRateCharge = number;
export type CRateDischarge = number;
export type CapacityKwh = number | null;
export type CapexPerKwh = number;
export type ChargeEfficiency = number;
export type Chemistry = "li_ion" | "kibam";
export type CalendarFadePctYr = number;
export type CycleFadePctPerEfc = number;
export type EndOfLifeCapacityPct = number;
export type DischargeEfficiency = number;
export type Enabled = boolean;
export type CRatio = number;
export type ChargeAcceptance = number;
export type KRate = number;
export type MaxChargeCurrentA = number;
export type NominalVoltageV = number;
export type LifetimeYears = number;
export type OpexPerKwhYr = number;
export type PowerKw = number | null;
export type SocInitial = number;
export type SocMax = number;
export type SocMin = number;
export type CapacityKw = number;
export type CapexPerKw = number;
export type Co2PerLiterKg = number;
export type Enabled1 = boolean;
export type FuelLhvKwhPerL = number;
export type FuelPricePerL = number;
export type InterceptLPerKwHr = number;
export type LifetimeYears1 = number;
export type MinDownHours = number;
export type MinLoadFraction = number;
export type MinUpHours = number;
export type OpexPerKwYr = number;
export type SlopeLPerKwh = number;
export type StartupCost = number;
export type ArrivalHour = number;
export type CapacityKwh1 = number;
export type Capex = number;
export type ChargeEfficiency1 = number;
export type DepartureHour = number;
export type DischargeEfficiency1 = number;
export type Enabled2 = boolean;
export type LifetimeKwh = number;
export type LifetimeYears2 = number;
export type MaxChargeKw = number;
export type MaxDischargeKw = number;
export type OpexPerYear = number;
export type PresenceCsvPath = string | null;
export type PresenceSource = "schedule" | "csv";
export type ReplacementCost = number;
export type SelfDischargeRate = number;
export type SocArrival = number;
export type SocDeparture = number;
export type SocInitial1 = number;
export type SocMax1 = number;
export type SocMin1 = number;
export type V2GEnabled = boolean;
export type WorkdaysPerWeek = number;
export type BoilerEfficiency = number;
export type Capex1 = number;
export type Co2PerKwhTh = number;
export type Enabled3 = boolean;
export type LifetimeYears3 = number;
export type MaxOutputKwTh = number | null;
export type OpexPerYear1 = number;
export type FlatRate = number | null;
export type MinChargePerMonth = number;
export type MonthlyServiceCharge = number;
export type RateType = "flat" | "seasonal" | "tiered";
export type SeasonalSchedule = GasSeasonalRate[] | null;
export type Months = number[];
export type Rate = number;
export type TieredLimitsKwhTh = number[] | null;
export type TieredRates = number[] | null;
export type Unit = "per_kwh_th" | "per_gj" | "per_mcf" | "per_therm";
export type CapacityKw1 = number;
export type Capex2 = number;
export type EmissionFactorKgPerKwh = number;
export type Enabled4 = boolean;
export type ExportAllowed = boolean;
export type ExportCapacityKw = number;
export type OpexYr = number;
export type AtmosphericPressureKpa = number;
export type Capex3 = number;
export type CoolingCapacityKw = number | null;
export type CopDatasetPath = string | null;
export type CopSource = "catalog" | "fixed" | "dataset";
export type Enabled5 = boolean;
export type FixedCopCooling = number | null;
export type FixedCopHeating = number | null;
export type HeatingCapacityKw = number | null;
export type IndoorDesignTempC = number;
export type IndoorHumidityRatio = number;
export type LifetimeYears4 = number;
export type Mode = "heating_only" | "cooling_only" | "both";
export type ModelName = string | null;
export type OpexPerYear2 = number;
export type Sizing = "catalog_auto" | "fixed";
export type StandbyPowerKw = number;
export type CapacityKw2 = number | null;
export type CapexPerKw1 = number;
export type Efficiency = number;
export type LifetimeYears5 = number;
export type OpexPerKwYr1 = number;
export type AzimuthDeg = number;
export type Bifaciality = number;
export type CapacityKw3 = number | null;
export type CapexPerKw2 = number;
export type DeratingFactor = number;
export type Enabled6 = boolean;
export type LifetimeYears6 = number;
export type ModuleType = "monofacial" | "bifacial";
export type NoctCelsius = number;
export type OpexPerKwYr2 = number;
export type TempCoeffPmax = number;
export type TiltDeg = number;
export type CapacityKwhTh = number | null;
export type CapacityMaxKwhTh = number;
export type CapacityMinKwhTh = number;
export type CapexPerKwhTh = number;
export type ChargePowerMaxKwTh = number | null;
export type CoolingCapacityKwhTh = number | null;
export type CoolingCapacityMaxKwhTh = number;
export type DischargePowerMaxKwTh = number | null;
export type Enabled7 = boolean;
export type IncludeCoolingStorage = boolean;
export type LifetimeYears7 = number;
export type LossRatePerHour = number;
export type OpexPerYear3 = number;
export type Sizing1 = "fixed" | "investment";
export type SocInitial2 = number;
export type SocMax2 = number;
export type SocMin2 = number;
export type CapexPerUnit = number;
export type Count = number;
export type Enabled8 = boolean;
export type HubHeightM = number;
export type LifetimeYears8 = number;
export type OpexPerUnitYr = number;
export type TurbineModel = string;
export type ForceGridDisconnect = boolean;
export type MaxAnnualDieselL = number | null;
export type MaxBatteryCyclesYr = number | null;
export type MaxLpsp = number;
export type MaxTotalEmissionsKg = number | null;
export type MinRenewableFraction = number;
export type ThermalLpspMax = number;
export type AnnualKwh = number | null;
export type CsvPath = string | null;
export type DailyProfile = number[] | null;
export type MonthlyPeak = number[] | null;
export type PeakMonth = string;
export type ScaleFactor = number;
export type Source =
  | "hourly_csv"
  | "daily_csv"
  | "monthly_total"
  | "monthly_hourly_average"
  | "annual_hourly_average"
  | "annual_daily_average"
  | "generic_monthly"
  | "generic_annual"
  | "generic_annual_total"
  | "generic"
  | "template";
export type TemplateName = string | null;
export type BuildingUaCoolKwPerK = number | null;
export type BuildingUaKwPerK = number | null;
export type CoolingCsvPath = string | null;
export type CoolingSetpointC = number;
export type DistributionEfficiency = number;
export type Enabled9 = boolean;
export type HeatingCsvPath = string | null;
export type HeatingSetpointC = number;
export type Source1 = "csv" | "degree_day";
export type AltitudeM = number;
export type Latitude = number;
export type Longitude = number;
export type Timezone = string;
export type EmissionsWeight = number;
export type Type = "cost" | "cost_and_emissions";
export type Budget = number | null;
export type CapexYear = number;
export type Currency = string;
export type DiscountRateNominal = number;
export type GridEscalationRate = number;
export type InflationRate = number;
export type LifetimeYears9 = number;
export type Name = string;
export type ReIncentiveRate = number;
export type Year = number;
export type SchemaVersion = string;
export type EndogenousTiering = boolean;
export type MonthlyRates = number[] | null;
export type MonthlyTiers = TierLevel[][] | null;
export type LimitKwh = number | null;
export type RatePerKwh = number;
export type RatePerKwh1 = number | null;
export type SeasonalSchedule1 = SeasonalRate[] | null;
export type Months1 = number[];
export type Name1 = string;
export type RatePerKwh2 = number;
export type SeasonalTiers = SeasonalTiers1[] | null;
export type Months2 = number[];
export type Name2 = string;
export type Tiers = TierLevel[];
export type Tiers1 = TierLevel[] | null;
export type TouSchedule = TouPeriod[] | null;
export type Hours = number[];
export type Months3 = number[];
export type Name3 = string;
export type RatePerKwh3 = number;
export type Weekday = boolean;
export type Weekend = boolean;
export type Type1 =
  | "flat"
  | "tou"
  | "tiered"
  | "seasonal"
  | "seasonal_tiered"
  | "monthly"
  | "monthly_tiered"
  | "ul_tou";
export type Hours1 = number[] | null;
export type RatePerKwMonth = number;
export type AnnualExcessCreditFraction = number;
export type Carryover = boolean;
export type Mode1 = "net_metering" | "net_billing";
export type MonthlyRates1 = number[] | null;
export type RatePerKwh4 = number | null;
export type TouSchedule1 = TouPeriod[] | null;
export type Type2 = "flat" | "tou" | "monthly";
export type MonthlyFlat = number | null;
export type Tiers2 = TierLevel[] | null;
export type Type3 = "flat" | "tiered_kwh";
export type CsvPath1 = string | null;
export type NsrdbApiKey = string | null;
export type NsrdbEmail = string | null;
export type Source2 = "csv" | "nsrdb";

/**
 * Root model for a SAMBA scenario file.
 */
export interface Scenario {
  components: Components;
  constraints?: Constraints;
  load: Load;
  location: Location;
  objective?: Objective;
  project: Project;
  schema_version?: SchemaVersion;
  tariff: Tariff;
  weather: Weather;
}
/**
 * Container for all system components.
 */
export interface Components {
  battery?: Battery | null;
  diesel_generator?: DieselGenerator | null;
  ev?: EV | null;
  gas_supply?: GasSupply | null;
  grid?: Grid | null;
  heat_pump?: HeatPump | null;
  inverter: Inverter;
  pv?: PV | null;
  thermal_storage?: ThermalStorage | null;
  wind_turbine?: WindTurbine | null;
}
/**
 * Battery energy storage configuration.
 */
export interface Battery {
  c_rate_charge?: CRateCharge;
  c_rate_discharge?: CRateDischarge;
  capacity_kwh?: CapacityKwh;
  capex_per_kwh: CapexPerKwh;
  charge_efficiency?: ChargeEfficiency;
  chemistry?: Chemistry;
  degradation?: BatteryDegradation | null;
  discharge_efficiency?: DischargeEfficiency;
  enabled?: Enabled;
  kibam?: KiBaMParams | null;
  lifetime_years?: LifetimeYears;
  opex_per_kwh_yr?: OpexPerKwhYr;
  power_kw?: PowerKw;
  soc_initial?: SocInitial;
  soc_max?: SocMax;
  soc_min?: SocMin;
}
/**
 * Capacity-fade model that derives the battery's replacement cadence (v4).
 *
 * When set, the battery's *effective* lifetime is computed from a linear fade
 * model (calendar + cycling) rather than the fixed ``lifetime_years`` nameplate:
 * annual fade [%] = ``calendar_fade_pct_yr`` + ``cycle_fade_pct_per_efc`` x
 * (annual equivalent full cycles), and the battery is replaced when cumulative
 * fade reaches ``end_of_life_capacity_pct``. EFC is derived from the solved
 * annual discharge throughput, so heavier cycling shortens life.
 */
export interface BatteryDegradation {
  calendar_fade_pct_yr?: CalendarFadePctYr;
  cycle_fade_pct_per_efc?: CycleFadePctPerEfc;
  end_of_life_capacity_pct?: EndOfLifeCapacityPct;
}
/**
 * Lead-acid KiBaM kinetic parameters (used when battery.chemistry == 'kibam').
 */
export interface KiBaMParams {
  c_ratio?: CRatio;
  charge_acceptance?: ChargeAcceptance;
  k_rate?: KRate;
  max_charge_current_a?: MaxChargeCurrentA;
  nominal_voltage_v?: NominalVoltageV;
}
/**
 * Diesel generator configuration.  Capacity is always fixed in v1.
 */
export interface DieselGenerator {
  capacity_kw: CapacityKw;
  capex_per_kw: CapexPerKw;
  co2_per_liter_kg?: Co2PerLiterKg;
  enabled?: Enabled1;
  fuel_lhv_kwh_per_l?: FuelLhvKwhPerL;
  fuel_price_per_l: FuelPricePerL;
  intercept_l_per_kw_hr?: InterceptLPerKwHr;
  lifetime_years?: LifetimeYears1;
  min_down_hours?: MinDownHours;
  min_load_fraction?: MinLoadFraction;
  min_up_hours?: MinUpHours;
  opex_per_kw_yr?: OpexPerKwYr;
  slope_l_per_kwh?: SlopeLPerKwh;
  startup_cost?: StartupCost;
}
/**
 * Electric vehicle smart-charging / V2G component.
 *
 * The EV battery is modeled as a :class:'solph.components.GenericStorage' on
 * the AC bus with time-varying charge/discharge bounds derived from a
 * presence schedule.  V2G discharge earns sell-tariff revenue when enabled.
 */
export interface EV {
  arrival_hour?: ArrivalHour;
  capacity_kwh: CapacityKwh1;
  capex?: Capex;
  charge_efficiency?: ChargeEfficiency1;
  departure_hour?: DepartureHour;
  discharge_efficiency?: DischargeEfficiency1;
  enabled?: Enabled2;
  lifetime_kwh?: LifetimeKwh;
  lifetime_years?: LifetimeYears2;
  max_charge_kw: MaxChargeKw;
  max_discharge_kw?: MaxDischargeKw;
  opex_per_year?: OpexPerYear;
  presence_csv_path?: PresenceCsvPath;
  presence_source?: PresenceSource;
  replacement_cost?: ReplacementCost;
  self_discharge_rate?: SelfDischargeRate;
  soc_arrival?: SocArrival;
  soc_departure?: SocDeparture;
  soc_initial?: SocInitial1;
  soc_max?: SocMax1;
  soc_min?: SocMin1;
  v2g_enabled?: V2GEnabled;
  workdays_per_week?: WorkdaysPerWeek;
}
/**
 * Natural gas supply configuration (Phase 23).
 *
 * Models a gas-fired boiler as an alternative or supplemental thermal source.
 * oemof topology::
 *
 *     [gas_supply Source] --gas_bus--> [gas_boiler Converter] --heat_bus--> demand
 */
export interface GasSupply {
  boiler_efficiency?: BoilerEfficiency;
  capex?: Capex1;
  co2_per_kwh_th?: Co2PerKwhTh;
  enabled?: Enabled3;
  lifetime_years?: LifetimeYears3;
  max_output_kw_th?: MaxOutputKwTh;
  opex_per_year?: OpexPerYear1;
  tariff?: GasTariff;
}
/**
 * Gas tariff structure -- supports flat, seasonal, and tiered pricing.
 */
export interface GasTariff {
  flat_rate?: FlatRate;
  min_charge_per_month?: MinChargePerMonth;
  monthly_service_charge?: MonthlyServiceCharge;
  rate_type?: RateType;
  seasonal_schedule?: SeasonalSchedule;
  tiered_limits_kwh_th?: TieredLimitsKwhTh;
  tiered_rates?: TieredRates;
  unit?: Unit;
}
/**
 * A gas rate band that applies to a fixed set of calendar months.
 */
export interface GasSeasonalRate {
  months: Months;
  rate: Rate;
}
/**
 * Grid connection configuration.
 */
export interface Grid {
  capacity_kw: CapacityKw1;
  capex?: Capex2;
  emission_factor_kg_per_kwh?: EmissionFactorKgPerKwh;
  enabled?: Enabled4;
  export_allowed?: ExportAllowed;
  export_capacity_kw?: ExportCapacityKw;
  opex_yr?: OpexYr;
}
/**
 * Air-source heat pump (electrically driven, reversible).
 *
 * Models the HP as one or two oemof ``Converter`` objects connecting the
 * AC bus to the heating / cooling thermal buses.  Hourly COP arrays are
 * pre-computed from outdoor temperature using a physics-based
 * (Carnot-fraction) model -- see :mod:`samba.thermal.cop`.
 *
 * Sizing modes
 * ------------
 * ``catalog_auto``  --  Automatically select the smallest catalog model
 *     whose rated capacity meets the peak thermal demand.  Requires thermal
 *     load peaks to be known (Phase 22).  Defaults to the smallest model
 *     (18000 BTU/hr) when no thermal load is configured.
 * ``fixed``  --  User specifies ``heating_capacity_kw`` /
 *     ``cooling_capacity_kw`` directly; ``model_name`` is optional.
 *
 * COP sources
 * -----------
 * ``catalog``  --  Physics-based Carnot-fraction COP curve evaluated against
 *     outdoor temperature (see :mod:`samba.thermal.cop`).
 * ``fixed``  --  Constant COP for all timesteps.  Requires
 *     ``fixed_cop_heating`` (if mode includes heating) and
 *     ``fixed_cop_cooling`` (if mode includes cooling).
 * ``dataset``  --  COP curves fitted from a user-supplied performance dataset
 *     CSV (``cop_dataset_path``); see :mod:`samba.thermal.cop_dataset`.
 */
export interface HeatPump {
  atmospheric_pressure_kpa?: AtmosphericPressureKpa;
  capex?: Capex3;
  cooling_capacity_kw?: CoolingCapacityKw;
  cop_dataset_path?: CopDatasetPath;
  cop_source?: CopSource;
  enabled?: Enabled5;
  fixed_cop_cooling?: FixedCopCooling;
  fixed_cop_heating?: FixedCopHeating;
  heating_capacity_kw?: HeatingCapacityKw;
  indoor_design_temp_c?: IndoorDesignTempC;
  indoor_humidity_ratio?: IndoorHumidityRatio;
  lifetime_years?: LifetimeYears4;
  mode?: Mode;
  model_name?: ModelName;
  opex_per_year?: OpexPerYear2;
  sizing?: Sizing;
  standby_power_kw?: StandbyPowerKw;
}
/**
 * AC/DC inverter configuration.
 */
export interface Inverter {
  capacity_kw?: CapacityKw2;
  capex_per_kw: CapexPerKw1;
  efficiency?: Efficiency;
  lifetime_years?: LifetimeYears5;
  opex_per_kw_yr?: OpexPerKwYr1;
}
/**
 * Photovoltaic array configuration.
 */
export interface PV {
  azimuth_deg?: AzimuthDeg;
  bifaciality?: Bifaciality;
  capacity_kw?: CapacityKw3;
  capex_per_kw: CapexPerKw2;
  derating_factor?: DeratingFactor;
  enabled?: Enabled6;
  lifetime_years?: LifetimeYears6;
  module_type?: ModuleType;
  noct_celsius?: NoctCelsius;
  opex_per_kw_yr?: OpexPerKwYr2;
  temp_coeff_pmax?: TempCoeffPmax;
  tilt_deg?: TiltDeg;
}
/**
 * Hot-water buffer tank or chilled-water thermal storage (Phase 21).
 *
 * The storage is modelled as an oemof ``GenericStorage`` on the heating
 * (and optionally cooling) thermal bus.  Energy losses are represented by a
 * fixed hourly fractional ``loss_rate_per_hour`` rather than temperature-
 * dependent physics (phase 21 simplification).
 *
 * Default ``loss_rate_per_hour = 0.002`` (0.2 %/h) corresponds roughly to a
 * well-insulated 200-L hot-water tank held at 60 °C in a 20 °C room:
 * ``Q_loss ≈ (1.5 m²) × (40 K) / (6 m²K/W) / (200 L × 0.00116 kWh/L/K) ≈ 0.2 %/h``.
 */
export interface ThermalStorage {
  capacity_kwh_th?: CapacityKwhTh;
  capacity_max_kwh_th?: CapacityMaxKwhTh;
  capacity_min_kwh_th?: CapacityMinKwhTh;
  capex_per_kwh_th?: CapexPerKwhTh;
  charge_power_max_kw_th?: ChargePowerMaxKwTh;
  cooling_capacity_kwh_th?: CoolingCapacityKwhTh;
  cooling_capacity_max_kwh_th?: CoolingCapacityMaxKwhTh;
  discharge_power_max_kw_th?: DischargePowerMaxKwTh;
  enabled?: Enabled7;
  include_cooling_storage?: IncludeCoolingStorage;
  lifetime_years?: LifetimeYears7;
  loss_rate_per_hour?: LossRatePerHour;
  opex_per_year?: OpexPerYear3;
  sizing?: Sizing1;
  soc_initial?: SocInitial2;
  soc_max?: SocMax2;
  soc_min?: SocMin2;
}
/**
 * Wind turbine configuration.
 */
export interface WindTurbine {
  capex_per_unit: CapexPerUnit;
  count?: Count;
  enabled?: Enabled8;
  hub_height_m?: HubHeightM;
  lifetime_years?: LifetimeYears8;
  opex_per_unit_yr?: OpexPerUnitYr;
  turbine_model: TurbineModel;
}
/**
 * Hard optimisation constraints.
 *
 * Every field here is a **hard** model constraint, not a KPI-only warning.
 * Violations cause the solver to reject candidate solutions outright.
 */
export interface Constraints {
  force_grid_disconnect?: ForceGridDisconnect;
  max_annual_diesel_l?: MaxAnnualDieselL;
  max_battery_cycles_yr?: MaxBatteryCyclesYr;
  max_lpsp?: MaxLpsp;
  max_total_emissions_kg?: MaxTotalEmissionsKg;
  min_renewable_fraction?: MinRenewableFraction;
  thermal_lpsp_max?: ThermalLpspMax;
}
/**
 * Electrical load profile configuration.
 */
export interface Load {
  annual_kwh?: AnnualKwh;
  csv_path?: CsvPath;
  daily_profile?: DailyProfile;
  monthly_peak?: MonthlyPeak;
  peak_month?: PeakMonth;
  scale_factor?: ScaleFactor;
  source: Source;
  template_name?: TemplateName;
  thermal?: ThermalLoad | null;
}
/**
 * Thermal load profile configuration.
 *
 * Supports two loading strategies:
 *
 * * ``"csv"`` -- supply hourly kW_th arrays directly as CSV files.
 * * ``"degree_day"`` -- derive heating/cooling demand from outdoor temperature
 *   using a per-degree heat-loss model parameterised by ``building_ua_kw_per_k``.
 *
 * Distribution efficiency
 * -----------------------
 * ``distribution_efficiency`` accounts for losses in the pipe/duct system
 * between the heat pump (or boiler) output and the point of demand.  The
 * thermal demand seen by the supply component equals
 * ``raw_demand / distribution_efficiency``.
 *
 * Thermal LPSP
 * -----------
 * When ``scenario.constraints.thermal_lpsp_max > 0`` the optimizer is
 * allowed to leave a fraction of thermal demand unmet (deficit drawn from
 * the ``heat_unmet`` / ``cool_unmet`` penalty sources).  Use this for
 * load-shedding studies.
 */
export interface ThermalLoad {
  building_ua_cool_kw_per_k?: BuildingUaCoolKwPerK;
  building_ua_kw_per_k?: BuildingUaKwPerK;
  cooling_csv_path?: CoolingCsvPath;
  cooling_setpoint_c?: CoolingSetpointC;
  distribution_efficiency?: DistributionEfficiency;
  enabled?: Enabled9;
  heating_csv_path?: HeatingCsvPath;
  heating_setpoint_c?: HeatingSetpointC;
  source?: Source1;
}
/**
 * Geographic location of the site.
 */
export interface Location {
  altitude_m?: AltitudeM;
  latitude: Latitude;
  longitude: Longitude;
  timezone: Timezone;
}
/**
 * Optimisation objective.
 *
 * type ''"cost"'' minimises NPC only (default, v1 behaviour).
 * type ''"cost_and_emissions"'' adds a carbon price (''emissions_weight'' $/kg CO2)
 * to both the diesel and grid import variable costs inside the LP objective, so the
 * solver trades off cost against emissions.  Use ''samba pareto'' to sweep over
 * ''emissions_weight'' values and generate a weighted-sum approximation of the
 * Pareto front.
 */
export interface Objective {
  emissions_weight?: EmissionsWeight;
  type?: Type;
}
/**
 * Top-level project / economic parameters.
 */
export interface Project {
  budget?: Budget;
  capex_year?: CapexYear;
  currency?: Currency;
  discount_rate_nominal: DiscountRateNominal;
  grid_escalation_rate?: GridEscalationRate;
  inflation_rate?: InflationRate;
  lifetime_years?: LifetimeYears9;
  name: Name;
  re_incentive_rate?: ReIncentiveRate;
  year?: Year;
}
/**
 * Electricity tariff definition.
 */
export interface Tariff {
  buy: BuyRate;
  demand_charge?: DemandCharge | null;
  nem?: NEM | null;
  sell?: SellRate | null;
  service_charge?: ServiceCharge | null;
}
/**
 * Electricity purchase rate from the grid (or notional off-grid price signal).
 */
export interface BuyRate {
  endogenous_tiering?: EndogenousTiering;
  monthly_rates?: MonthlyRates;
  monthly_tiers?: MonthlyTiers;
  rate_per_kwh?: RatePerKwh1;
  seasonal_schedule?: SeasonalSchedule1;
  seasonal_tiers?: SeasonalTiers;
  tiers?: Tiers1;
  tou_schedule?: TouSchedule;
  type: Type1;
}
/**
 * A single consumption tier (for tiered electricity rates).
 */
export interface TierLevel {
  limit_kwh?: LimitKwh;
  rate_per_kwh: RatePerKwh;
}
/**
 * A flat rate that applies during a specific set of months (season).
 */
export interface SeasonalRate {
  months: Months1;
  name: Name1;
  rate_per_kwh: RatePerKwh2;
}
/**
 * A tiered rate that applies during a specific set of months (season).
 */
export interface SeasonalTiers1 {
  months: Months2;
  name: Name2;
  tiers: Tiers;
}
/**
 * A single time-of-use pricing period.
 */
export interface TouPeriod {
  hours: Hours;
  months?: Months3;
  name: Name3;
  rate_per_kwh: RatePerKwh3;
  weekday?: Weekday;
  weekend?: Weekend;
}
/**
 * Demand charge on the monthly peak grid import [$/kW-month].
 *
 * The charge is applied to the highest grid-import power reached in each
 * calendar month (optionally restricted to ``hours``).  It is modelled inside
 * the LP as a per-month peak variable, so the solver has an incentive to shave
 * peaks (e.g. by discharging storage) rather than merely being billed for them.
 */
export interface DemandCharge {
  hours?: Hours1;
  rate_per_kw_month: RatePerKwMonth;
}
/**
 * Annual net-metering / net-billing credit reconciliation.
 *
 * Without this, SAMBA nets grid cost annually as ``bought$ − sold$``, letting
 * unlimited export revenue offset import cost. Real NEM tariffs instead bill
 * **per calendar month** with a **$0 floor**, roll surplus export credit forward,
 * and settle whatever credit remains at year end. This model captures those
 * three behaviours (all monetary; the export valuation is whatever the user puts
 * in the ``sell`` rate, so ``mode`` is intent/labelling):
 *
 * - ``net_metering``: exports typically credited at (near) retail — set ``sell``
 *   equal to the buy rate.
 * - ``net_billing``: exports valued at a lower export rate — set ``sell`` accordingly.
 *
 * Reconciliation each month: ``net$ = bought$ − sold$``; apply any carried
 * credit; the monthly bill is floored at $0; surplus becomes credit (carried
 * forward if ``carryover``). At year end, leftover credit is paid back to the
 * customer scaled by ``annual_excess_credit_fraction`` (0 = forfeited, the common
 * default; 1 = full cash-out).
 */
export interface NEM {
  annual_excess_credit_fraction?: AnnualExcessCreditFraction;
  carryover?: Carryover;
  mode?: Mode1;
}
/**
 * Electricity export / sell rate to the grid (feed-in tariff).
 */
export interface SellRate {
  monthly_rates?: MonthlyRates1;
  rate_per_kwh?: RatePerKwh4;
  tou_schedule?: TouSchedule1;
  type: Type2;
}
/**
 * Fixed monthly service / standing charge.
 *
 * Note: demand-based service charges ($/kW of monthly peak) are out of scope for v1-v2
 * and are deferred to v3+.
 */
export interface ServiceCharge {
  monthly_flat?: MonthlyFlat;
  tiers?: Tiers2;
  type: Type3;
}
/**
 * Weather data source configuration.
 *
 * - ``"csv"``: load a local NSRDB-format CSV (``csv_path``).
 * - ``"nsrdb"`` (v4): fetch a year of NSRDB data from the NREL API for the
 *   scenario ``location`` and ``project.year``, cached locally so runs are
 *   reproducible and offline-repeatable. Requires ``nsrdb_api_key`` (or the
 *   ``NREL_API_KEY`` environment variable).
 */
export interface Weather {
  csv_path?: CsvPath1;
  nsrdb_api_key?: NsrdbApiKey;
  nsrdb_email?: NsrdbEmail;
  source: Source2;
}
