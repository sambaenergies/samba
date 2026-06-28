/* eslint-disable */
/**
 * AUTO-GENERATED from ../../../schemas by `npm run gen:types`. DO NOT EDIT.
 * Source of truth: backend Pydantic models (see scripts/export_schemas.py).
 */

export type ActiveJobs = number;
export type Solver = string;
export type SolverReady = boolean;
export type Status = "ok";
export type Version = string;

/**
 * Response body for ''GET /api/v1/health''.
 *
 * Attributes
 * ----------
 * status:
 *     Always ''"ok"'' when the service is running.
 * version:
 *     Installed ''samba-core'' package version string.
 * solver:
 *     Configured solver name (from :attr:'~samba_service.config.ServiceConfig.solver').
 * solver_ready:
 *     ''True'' when the configured solver binary/package is importable.
 * active_jobs:
 *     Number of jobs currently in ''PENDING'' or ''RUNNING'' state.
 */
export interface HealthResponse {
  active_jobs?: ActiveJobs;
  solver: Solver;
  solver_ready: SolverReady;
  status?: Status;
  version: Version;
}
