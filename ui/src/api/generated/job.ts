/* eslint-disable */
/**
 * AUTO-GENERATED from ../../../schemas by `npm run gen:types`. DO NOT EDIT.
 * Source of truth: backend Pydantic models (see scripts/export_schemas.py).
 */

export type Artifacts = string[];
export type CompletedAt = string | null;
export type Error = string | null;
export type AnnualCoolProducedKwh = number;
export type AnnualCoolingDemandKwhTh = number;
export type AnnualDemandChargeUsd = number;
export type AnnualEnergyNetUsd = number;
export type AnnualEvChargeKwh = number;
export type AnnualEvDischargeKwh = number;
export type AnnualGasCo2Kg = number;
export type AnnualGasConsumptionKwhTh = number;
export type AnnualGasCostUsd = number;
export type AnnualHeatProducedKwh = number;
export type AnnualHeatingDemandKwhTh = number;
export type AnnualHpElecKwh = number;
export type AnnualThermalStorageCycles = number;
export type AnnualThroughputCycles = number;
export type BatteryEolYear = number;
export type Crf = number;
export type DgEmissionsKg = number;
export type DgFuelConsumptionLiters = number;
export type DgOperatingHours = number;
export type EvV2GRevenue = number;
export type GasBoilerCapex = number;
export type GasBoilerNpc = number;
export type GridEmissionsKg = number;
export type HpModelName = string;
export type InitialInvestment = number;
export type KpiContractVersion = string;
export type Lcoe = number;
export type Lem = number;
export type Lpsp = number;
export type MeanCopCooling = number;
export type MeanCopHeating = number;
export type MonthlyGridCost = number[];
export type MonthlyGridKwh = number[];
export type Npc = number;
export type OperatingCost = number;
export type PeakDemandKwByMonth = number[];
export type RenewableFraction = number;
export type ThermalLpspCooling = number;
export type ThermalLpspHeating = number;
export type ThermalStorageCapex = number;
export type ThermalStorageCoolingKwhTh = number;
export type ThermalStorageHeatingKwhTh = number;
export type TotalBatteryCharge = number;
export type TotalBatteryDischarge = number;
export type TotalDgGeneration = number;
export type TotalEmissionsKg = number;
export type TotalEnergyDump = number;
export type TotalFuelCost = number;
export type TotalGridBought = number;
export type TotalGridCostNet = number;
export type TotalGridSold = number;
export type TotalLoadServed = number;
export type TotalOmCost = number;
export type TotalPvGeneration = number;
export type TotalReplacementCost = number;
export type TotalSalvage = number;
export type TotalUnmetLoad = number;
export type TotalWtGeneration = number;
export type RunId = string;
export type Sizing = SizingRow[] | null;
export type Capacity = number;
export type CapitalCost = number;
export type Component = string;
export type Count = number;
export type Unit = string;
export type SolveTimeS = number | null;
export type StartedAt = string | null;
/**
 * Life-cycle state of a background solve job.
 */
export type JobStatus = "pending" | "running" | "completed" | "failed";
export type SubmittedAt = string;

/**
 * Response body for ''GET /api/v1/jobs/{run_id}''.
 *
 * Attributes
 * ----------
 * run_id:
 *     UUID4 job identifier.
 * status:
 *     Current :class:'~samba_service.jobs.JobStatus'.
 * submitted_at:
 *     UTC timestamp of job submission.
 * started_at:
 *     UTC timestamp when the solver thread picked up the job, or ''None''.
 * completed_at:
 *     UTC timestamp of job completion (success or failure), or ''None''.
 * kpis:
 *     Typed :class:'~samba.run_result.contracts.KpiSummary'.  Present only when
 *     ''status == "completed"''.  Degraded to ''None'' (with a logged warning)
 *     if a persisted legacy row's stored KPIs no longer match the contract.
 * sizing:
 *     List of typed :class:'~samba.run_result.contracts.SizingRow'.  Present
 *     only when ''status == "completed"''; degraded as above on legacy rows.
 * artifacts:
 *     List of downloadable filenames available under
 *     ''GET /api/v1/jobs/{run_id}/artifacts/{filename}''.
 *     Populated only when ''status == "completed"''.
 * error:
 *     Human-readable error description when ''status == "failed"''.
 */
export interface JobStatusResponse {
  artifacts?: Artifacts;
  completed_at?: CompletedAt;
  error?: Error;
  kpis?: KpiSummary | null;
  run_id: RunId;
  sizing?: Sizing;
  solve_time_s?: SolveTimeS;
  started_at?: StartedAt;
  status: JobStatus;
  submitted_at: SubmittedAt;
}
/**
 * Mirrors ``kpis.json`` (the dict from :func:`samba.run_result.kpis.compute_kpis`).
 *
 * The key set is fixed: heat-pump / thermal / gas KPIs default to zero (or an
 * empty string) when those components are not modelled, rather than being
 * omitted. ``renewable_fraction``, ``lpsp``, and ``lem`` are fractions in
 * ``[0, 1]`` (the UI renders the first two as percentages).
 */
export interface KpiSummary {
  annual_cool_produced_kwh: AnnualCoolProducedKwh;
  annual_cooling_demand_kwh_th: AnnualCoolingDemandKwhTh;
  annual_demand_charge_usd: AnnualDemandChargeUsd;
  annual_energy_net_usd: AnnualEnergyNetUsd;
  annual_ev_charge_kwh: AnnualEvChargeKwh;
  annual_ev_discharge_kwh: AnnualEvDischargeKwh;
  annual_gas_co2_kg: AnnualGasCo2Kg;
  annual_gas_consumption_kwh_th: AnnualGasConsumptionKwhTh;
  annual_gas_cost_usd: AnnualGasCostUsd;
  annual_heat_produced_kwh: AnnualHeatProducedKwh;
  annual_heating_demand_kwh_th: AnnualHeatingDemandKwhTh;
  annual_hp_elec_kwh: AnnualHpElecKwh;
  annual_thermal_storage_cycles: AnnualThermalStorageCycles;
  annual_throughput_cycles: AnnualThroughputCycles;
  battery_eol_year: BatteryEolYear;
  crf: Crf;
  dg_emissions_kg: DgEmissionsKg;
  dg_fuel_consumption_liters: DgFuelConsumptionLiters;
  dg_operating_hours: DgOperatingHours;
  ev_v2g_revenue: EvV2GRevenue;
  gas_boiler_capex: GasBoilerCapex;
  gas_boiler_npc: GasBoilerNpc;
  grid_emissions_kg: GridEmissionsKg;
  hp_model_name: HpModelName;
  initial_investment: InitialInvestment;
  kpi_contract_version: KpiContractVersion;
  lcoe: Lcoe;
  lem: Lem;
  lpsp: Lpsp;
  mean_cop_cooling: MeanCopCooling;
  mean_cop_heating: MeanCopHeating;
  monthly_grid_cost: MonthlyGridCost;
  monthly_grid_kwh: MonthlyGridKwh;
  npc: Npc;
  operating_cost: OperatingCost;
  peak_demand_kw_by_month: PeakDemandKwByMonth;
  renewable_fraction: RenewableFraction;
  thermal_lpsp_cooling: ThermalLpspCooling;
  thermal_lpsp_heating: ThermalLpspHeating;
  thermal_storage_capex: ThermalStorageCapex;
  thermal_storage_cooling_kwh_th: ThermalStorageCoolingKwhTh;
  thermal_storage_heating_kwh_th: ThermalStorageHeatingKwhTh;
  total_battery_charge: TotalBatteryCharge;
  total_battery_discharge: TotalBatteryDischarge;
  total_dg_generation: TotalDgGeneration;
  total_emissions_kg: TotalEmissionsKg;
  total_energy_dump: TotalEnergyDump;
  total_fuel_cost: TotalFuelCost;
  total_grid_bought: TotalGridBought;
  total_grid_cost_net: TotalGridCostNet;
  total_grid_sold: TotalGridSold;
  total_load_served: TotalLoadServed;
  total_om_cost: TotalOmCost;
  total_pv_generation: TotalPvGeneration;
  total_replacement_cost: TotalReplacementCost;
  total_salvage: TotalSalvage;
  total_unmet_load: TotalUnmetLoad;
  total_wt_generation: TotalWtGeneration;
}
/**
 * One row of ``sizing.csv`` (the optimiser's chosen component sizing).
 */
export interface SizingRow {
  capacity: Capacity;
  capital_cost: CapitalCost;
  component: Component;
  count: Count;
  unit: Unit;
}
