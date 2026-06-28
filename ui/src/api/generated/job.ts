/* eslint-disable */
/**
 * AUTO-GENERATED from ../../../schemas by `npm run gen:types`. DO NOT EDIT.
 * Source of truth: backend Pydantic models (see scripts/export_schemas.py).
 */

export type Artifacts = string[];
export type CompletedAt = string | null;
export type Error = string | null;
export type Kpis = {
  [k: string]: unknown;
} | null;
export type RunId = string;
export type Sizing =
  | {
      [k: string]: unknown;
    }[]
  | null;
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
 *     KPI dict (28 fields).  Present only when ''status == "completed"''.
 * sizing:
 *     List of sizing records.  Present only when ''status == "completed"''.
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
  kpis?: Kpis;
  run_id: RunId;
  sizing?: Sizing;
  solve_time_s?: SolveTimeS;
  started_at?: StartedAt;
  status: JobStatus;
  submitted_at: SubmittedAt;
}
