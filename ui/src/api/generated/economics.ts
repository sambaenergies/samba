/* eslint-disable */
/**
 * AUTO-GENERATED from ../../../schemas by `npm run gen:types`. DO NOT EDIT.
 * Source of truth: backend Pydantic models (see scripts/export_schemas.py).
 */

export type Fuel = number;
export type GridNet = number;
export type Investment = number;
export type Om = number;
export type Replacement = number;
export type Salvage = number;
export type Total = number;
export type Year = number;
export type CashflowAnnual = CashflowYear[];
export type Crf = number;
export type DiscountRateReal = number;
export type Npc = number;
export type ProjectLifetimeYears = number;

/**
 * Mirrors ``economics.json`` (from :func:`samba.economics.cashflow.build_economics`).
 *
 * The per-year ``cashflow_annual`` table and the top-level scalars are the
 * drift-sensitive contract the UI consumes. The cost breakdowns
 * (``investment``, ``om_annual_npv``, …) are backend-internal aggregates kept
 * loosely typed so internal accounting changes do not needlessly break the gate.
 */
export interface EconomicsReport {
  cashflow_annual: CashflowAnnual;
  crf: Crf;
  discount_rate_real: DiscountRateReal;
  fuel: Fuel1;
  gas: Gas;
  grid: Grid;
  investment: Investment1;
  npc: Npc;
  om_annual_npv: OmAnnualNpv;
  project_lifetime_years: ProjectLifetimeYears;
  replacement_schedule: ReplacementSchedule;
  salvage: Salvage1;
}
/**
 * One row of ``economics.json`` ``cashflow_annual`` (per project year).
 */
export interface CashflowYear {
  fuel: Fuel;
  grid_net: GridNet;
  investment: Investment;
  om: Om;
  replacement: Replacement;
  salvage: Salvage;
  total: Total;
  year: Year;
}
export interface Fuel1 {
  [k: string]: number;
}
export interface Gas {
  [k: string]: number;
}
export interface Grid {
  [k: string]: number;
}
export interface Investment1 {
  [k: string]: number;
}
export interface OmAnnualNpv {
  [k: string]: number;
}
export interface ReplacementSchedule {
  [k: string]: {
    [k: string]: number;
  };
}
export interface Salvage1 {
  [k: string]: number;
}
