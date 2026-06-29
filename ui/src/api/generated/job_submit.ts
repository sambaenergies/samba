/* eslint-disable */
/**
 * AUTO-GENERATED from ui/contract by `npm run gen:types`. DO NOT EDIT.
 * Source of truth: backend Pydantic models (see scripts/export_schemas.py).
 */

export type PollUrl = string;
export type RunId = string;
export type Status = "pending";

/**
 * Response body for ''POST /api/v1/jobs'' (HTTP 202 Accepted).
 *
 * Attributes
 * ----------
 * run_id:
 *     UUID4 string identifying the submitted job.
 * status:
 *     Initial status -- always ''"pending"'' immediately after submission.
 * poll_url:
 *     Relative URL for polling job state:
 *     ''/api/v1/jobs/{run_id}''.
 */
export interface JobSubmitResponse {
  poll_url: PollUrl;
  run_id: RunId;
  status?: Status;
}
