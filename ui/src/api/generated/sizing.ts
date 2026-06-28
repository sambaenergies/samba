/* eslint-disable */
/**
 * AUTO-GENERATED from ../../../schemas by `npm run gen:types`. DO NOT EDIT.
 * Source of truth: backend Pydantic models (see scripts/export_schemas.py).
 */

export type Capacity = number;
export type CapitalCost = number;
export type Component = string;
export type Count = number;
export type Unit = string;

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
