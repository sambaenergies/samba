// ---------------------------------------------------------------------------
// Generated contracts (single source of truth: backend Pydantic models).
// Do not hand-edit these shapes here — change the model + `just schemas`, then
// `npm run gen:types`. See src/api/generated/*.ts.
// ---------------------------------------------------------------------------
import type { CashflowYear, EconomicsReport } from "./generated/economics";
import type { DispatchContract } from "./generated/dispatch";
import type { HealthResponse } from "./generated/health";
import type { JobStatus, JobStatusResponse } from "./generated/job";
import type { KpiSummary } from "./generated/kpis";
import type {
  Battery,
  Components,
  Constraints,
  DieselGenerator,
  EV,
  GasSupply,
  Grid,
  HeatPump,
  Inverter,
  Load,
  Location,
  Objective,
  Project,
  PV,
  Scenario,
  Tariff,
  ThermalStorage,
  Weather,
  WindTurbine,
} from "./generated/scenario";
import type { SizingRow } from "./generated/sizing";
import type { ValidateResponse } from "./generated/validate";

export type { CashflowYear, EconomicsReport, DispatchContract, HealthResponse, KpiSummary, SizingRow };
export type { JobStatus, JobStatusResponse };

/** A job record as returned by the service (alias of the generated contract). */
export type JobRecord = JobStatusResponse;

/** Validation response from POST /api/v1/validate (alias of the generated contract). */
export type ValidationResponse = ValidateResponse;
export type {
  Battery,
  Components,
  Constraints,
  DieselGenerator,
  EV,
  GasSupply,
  Grid,
  HeatPump,
  Inverter,
  Load,
  Location,
  Objective,
  Project,
  PV,
  Scenario,
  Tariff,
  ThermalStorage,
  Weather,
  WindTurbine,
};

/** The editor's working draft is a full backend Scenario (generated type). */
export type ScenarioDraft = Scenario;

/** Parsed dispatch view-model (alias of the generated contract). */
export type DispatchData = DispatchContract;

/** Cashflow row as charted: the generated per-year contract plus the UI-computed cumulative NPV. */
export interface CashflowRow extends CashflowYear {
  cumulative_npv: number;
}

/** UI-internal normalized validation error (from normalizeValidationErrors). */
export interface ValidationError {
  path: string[];
  message: string;
  severity: "error" | "warning";
}

export interface MonthlyRow {
  month: number;
  pv_kwh: number;
  wind_kwh: number;
  battery_discharge_kwh: number;
  diesel_kwh: number;
  grid_import_kwh: number;
  load_kwh: number;
  grid_export_kwh: number;
  unmet_kwh: number;
}

