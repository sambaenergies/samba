/* eslint-disable */
/**
 * AUTO-GENERATED from ui/contract by `npm run gen:types`. DO NOT EDIT.
 * Source of truth: backend Pydantic models (see scripts/export_schemas.py).
 */

export type Timestamps = string[];

/**
 * Shape of the parsed ``dispatch.csv`` time-series the UI charts.
 *
 * The dispatch frame is wide and its columns vary by scenario, so this models
 * the envelope (a timestamp index plus named numeric series) rather than a
 * fixed column set. ``KNOWN_SERIES`` documents the series the UI knows how to
 * label/colour; unknown series are still rendered generically.
 */
export interface DispatchContract {
  series: Series;
  timestamps: Timestamps;
}
export interface Series {
  [k: string]: number[];
}
