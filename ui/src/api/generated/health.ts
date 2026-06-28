/* eslint-disable */
/**
 * AUTO-GENERATED from ../../../schemas by `npm run gen:types`. DO NOT EDIT.
 * Source of truth: backend Pydantic models (see scripts/export_schemas.py).
 */

export type ActiveJobs = number;
export type ApiVersion = string;
export type Capabilities = string[];
export type ContractVersion = string;
export type Solver = string;
export type SolverReady = boolean;
export type Status = "ok";
export type Version = string;

/**
 * Response body for ''GET /health'' (public, unversioned liveness probe).
 *
 * Attributes
 * ----------
 * status:
 *     Always ''"ok"'' when the service is running.
 * version:
 *     Installed ''samba-core'' package version string. **Display only** — do not
 *     key API compatibility off it.
 * api_version:
 *     SemVer of the HTTP API surface (equals the OpenAPI ''info.version''); the
 *     value an external client checks for compatibility. From
 *     :data:'samba_service._contract.API_VERSION'.
 * contract_version:
 *     Version of the published data/schema contract (OpenAPI + companion JSON
 *     Schemas) the client generated its types from. From
 *     :data:'samba_service._contract.CONTRACT_VERSION'.
 * capabilities:
 *     Stable advertised feature flags the client may branch on
 *     (:data:'samba_service._contract.CAPABILITIES').
 * solver:
 *     Configured solver name (from :attr:'~samba_service.config.ServiceConfig.solver').
 * solver_ready:
 *     ''True'' when the configured solver binary/package is importable.
 * active_jobs:
 *     Number of jobs currently in ''PENDING'' or ''RUNNING'' state.
 *
 * The three version axes (samba-core package, API/contract, and the OpenAPI
 * spec version owned by FastAPI) are documented in
 * :mod:'samba_service._contract'.
 */
export interface HealthResponse {
  active_jobs?: ActiveJobs;
  api_version: ApiVersion;
  capabilities: Capabilities;
  contract_version: ContractVersion;
  solver: Solver;
  solver_ready: SolverReady;
  status?: Status;
  version: Version;
}
