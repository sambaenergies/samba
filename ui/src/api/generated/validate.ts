/* eslint-disable */
/**
 * AUTO-GENERATED from ui/contract by `npm run gen:types`. DO NOT EDIT.
 * Source of truth: backend Pydantic models (see scripts/export_schemas.py).
 */

export type Errors = string[];
export type Valid = boolean;

/**
 * Response body for ''POST /api/v1/validate''.
 *
 * Attributes
 * ----------
 * valid:
 *     ''True'' when the scenario passes all schema checks.
 * errors:
 *     List of ''"field.path: message"'' strings describing every validation
 *     failure.  Empty when ''valid is True''.
 */
export interface ValidateResponse {
  errors?: Errors;
  valid: Valid;
}
