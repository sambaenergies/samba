/* eslint-disable */
/**
 * AUTO-GENERATED from ui/contract by `npm run gen:types`. DO NOT EDIT.
 * Source of truth: backend Pydantic models (see scripts/export_schemas.py).
 */

export type Detail = string;
export type Errors = string[] | null;

/**
 * Shared envelope for every non-2xx response.
 *
 * Attributes
 * ----------
 * detail:
 *     Human-readable summary of the failure (the FastAPI default error key).
 * errors:
 *     Optional per-item failure lines. For scenario-validation failures this
 *     is ''ScenarioValidationError.format_errors().splitlines()'' -- the **same
 *     list** ''POST /api/v1/validate'' returns in its 200 body for the same
 *     input -- so a client can render field errors identically regardless of
 *     which endpoint rejected the scenario. ''None'' for errors that have no
 *     line-level breakdown (404 / 409 / 401 / generic 400).
 */
export interface ErrorResponse {
  detail: Detail;
  errors?: Errors;
}
