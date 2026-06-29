/* eslint-disable */
/**
 * AUTO-GENERATED from ui/contract by `npm run gen:types`. DO NOT EDIT.
 * Source of truth: backend Pydantic models (see scripts/export_schemas.py).
 */

export interface paths {
    "/api/v1/jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List all jobs
         * @description Return all job records, sorted by submission time descending.
         *
         *     Use the optional ''?status='' query parameter to filter.
         */
        get: operations["listJobs"];
        put?: never;
        /**
         * Submit an async optimisation job
         * @description Validate the scenario dict and enqueue an async solve job.
         *
         *     Returns HTTP 202 with ''run_id'' immediately.  Poll
         *     ''GET /api/v1/jobs/{run_id}'' for status.
         */
        post: operations["submitJob"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Poll job status
         * @description Return the current status of a submitted job.
         */
        get: operations["getJob"];
        put?: never;
        post?: never;
        /**
         * Delete a job record
         * @description Remove a job from the in-process store.
         *
         *     Optionally delete the on-disk artifact directory when
         *     ''?delete_artifacts=true''.  Returns HTTP 204 on success.
         */
        delete: operations["deleteJob"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/jobs/{run_id}/artifacts/{filename}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download a result artifact
         * @description Stream a result file from the job's artifact directory.
         *
         *     Allowed filenames: ''scenario.yaml'', ''kpis.json'', ''sizing.csv'',
         *     ''dispatch.parquet'', ''dispatch.csv'', ''economics.json'',
         *     ''annual_summary.csv'', ''tariff.parquet'', ''metadata.json'',
         *     ''solver.log''.
         *
         *     Returns HTTP 400 on any path-traversal attempt.
         */
        get: operations["getArtifact"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/validate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Validate a scenario
         * @description Validate *request.scenario* against the SAMBA Pydantic schema.
         *
         *     Always returns HTTP 200; check the ''valid'' field in the response.
         */
        post: operations["validateScenario"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Service health check
         * @description Returns service status, samba-core version, API/contract version, advertised capabilities, solver availability, and active job count.
         */
        get: operations["getHealth"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * ErrorResponse
         * @description Shared envelope for every non-2xx response.
         *
         *     Attributes
         *     ----------
         *     detail:
         *         Human-readable summary of the failure (the FastAPI default error key).
         *     errors:
         *         Optional per-item failure lines. For scenario-validation failures this
         *         is ''ScenarioValidationError.format_errors().splitlines()'' -- the **same
         *         list** ''POST /api/v1/validate'' returns in its 200 body for the same
         *         input -- so a client can render field errors identically regardless of
         *         which endpoint rejected the scenario. ''None'' for errors that have no
         *         line-level breakdown (404 / 409 / 401 / generic 400).
         */
        ErrorResponse: {
            /** Detail */
            detail: string;
            /** Errors */
            errors?: string[] | null;
        };
        /**
         * HealthResponse
         * @description Response body for ''GET /health'' (public, unversioned liveness probe).
         *
         *     Attributes
         *     ----------
         *     status:
         *         Always ''"ok"'' when the service is running.
         *     version:
         *         Installed ''samba-core'' package version string. **Display only** — do not
         *         key API compatibility off it.
         *     api_version:
         *         SemVer of the HTTP API surface (equals the OpenAPI ''info.version''); the
         *         value an external client checks for compatibility. From
         *         :data:'samba_service._contract.API_VERSION'.
         *     contract_version:
         *         Version of the published data/schema contract (OpenAPI + companion JSON
         *         Schemas) the client generated its types from. From
         *         :data:'samba_service._contract.CONTRACT_VERSION'.
         *     capabilities:
         *         Stable advertised feature flags the client may branch on
         *         (:data:'samba_service._contract.CAPABILITIES').
         *     solver:
         *         Configured solver name (from :attr:'~samba_service.config.ServiceConfig.solver').
         *     solver_ready:
         *         ''True'' when the configured solver binary/package is importable.
         *     active_jobs:
         *         Number of jobs currently in ''PENDING'' or ''RUNNING'' state.
         *
         *     The three version axes (samba-core package, API/contract, and the OpenAPI
         *     spec version owned by FastAPI) are documented in
         *     :mod:'samba_service._contract'.
         */
        HealthResponse: {
            /**
             * Active Jobs
             * @default 0
             */
            active_jobs: number;
            /** Api Version */
            api_version: string;
            /** Capabilities */
            capabilities: string[];
            /** Contract Version */
            contract_version: string;
            /** Solver */
            solver: string;
            /** Solver Ready */
            solver_ready: boolean;
            /**
             * Status
             * @default ok
             * @constant
             */
            status: "ok";
            /** Version */
            version: string;
        };
        /**
         * JobStatus
         * @description Life-cycle state of a background solve job.
         * @enum {string}
         */
        JobStatus: "pending" | "running" | "completed" | "failed";
        /**
         * JobStatusResponse
         * @description Response body for ''GET /api/v1/jobs/{run_id}''.
         *
         *     Attributes
         *     ----------
         *     run_id:
         *         UUID4 job identifier.
         *     status:
         *         Current :class:'~samba_service.jobs.JobStatus'.
         *     submitted_at:
         *         UTC timestamp of job submission.
         *     started_at:
         *         UTC timestamp when the solver thread picked up the job, or ''None''.
         *     completed_at:
         *         UTC timestamp of job completion (success or failure), or ''None''.
         *     kpis:
         *         Typed :class:'~samba.run_result.contracts.KpiSummary'.  Present only when
         *         ''status == "completed"''.  Degraded to ''None'' (with a logged warning)
         *         if a persisted legacy row's stored KPIs no longer match the contract.
         *     sizing:
         *         List of typed :class:'~samba.run_result.contracts.SizingRow'.  Present
         *         only when ''status == "completed"''; degraded as above on legacy rows.
         *     artifacts:
         *         List of downloadable filenames available under
         *         ''GET /api/v1/jobs/{run_id}/artifacts/{filename}''.
         *         Populated only when ''status == "completed"''.
         *     error:
         *         Human-readable error description when ''status == "failed"''.
         */
        JobStatusResponse: {
            /**
             * Artifacts
             * @default []
             */
            artifacts: string[];
            /** Completed At */
            completed_at?: string | null;
            /** Error */
            error?: string | null;
            kpis?: components["schemas"]["KpiSummary"] | null;
            /** Run Id */
            run_id: string;
            /** Sizing */
            sizing?: components["schemas"]["SizingRow"][] | null;
            /** Solve Time S */
            solve_time_s?: number | null;
            /** Started At */
            started_at?: string | null;
            status: components["schemas"]["JobStatus"];
            /**
             * Submitted At
             * Format: date-time
             */
            submitted_at: string;
        };
        /**
         * JobSubmitRequest
         * @description Request body for ''POST /api/v1/jobs''.
         *
         *     Attributes
         *     ----------
         *     scenario:
         *         Raw scenario mapping with the same structure as a scenario YAML file
         *         (''schema_version'', ''project'', ''load'', ''components'', etc.).
         *     run_dir_name:
         *         Optional custom stem for the run output directory.  When ''None'',
         *         the service creates a subdirectory named by the job's ''run_id''.
         */
        JobSubmitRequest: {
            /** Run Dir Name */
            run_dir_name?: string | null;
            /**
             * Scenario
             * @description Scenario mapping with the same structure as a scenario YAML file (schema_version, project, location, load, components, tariff, ...). Validated against the SAMBA Scenario model; see scenario.schema.json for the full shape.
             */
            scenario: {
                [key: string]: unknown;
            };
        };
        /**
         * JobSubmitResponse
         * @description Response body for ''POST /api/v1/jobs'' (HTTP 202 Accepted).
         *
         *     Attributes
         *     ----------
         *     run_id:
         *         UUID4 string identifying the submitted job.
         *     status:
         *         Initial status -- always ''"pending"'' immediately after submission.
         *     poll_url:
         *         Relative URL for polling job state:
         *         ''/api/v1/jobs/{run_id}''.
         */
        JobSubmitResponse: {
            /** Poll Url */
            poll_url: string;
            /** Run Id */
            run_id: string;
            /**
             * Status
             * @default pending
             * @constant
             */
            status: "pending";
        };
        /**
         * KpiSummary
         * @description Mirrors ``kpis.json`` (the dict from :func:`samba.run_result.kpis.compute_kpis`).
         *
         *     The key set is fixed: heat-pump / thermal / gas KPIs default to zero (or an
         *     empty string) when those components are not modelled, rather than being
         *     omitted. ``renewable_fraction``, ``lpsp``, and ``lem`` are fractions in
         *     ``[0, 1]`` (the UI renders the first two as percentages).
         */
        KpiSummary: {
            /** Annual Cool Produced Kwh */
            annual_cool_produced_kwh: number;
            /** Annual Cooling Demand Kwh Th */
            annual_cooling_demand_kwh_th: number;
            /** Annual Demand Charge Usd */
            annual_demand_charge_usd: number;
            /** Annual Energy Net Usd */
            annual_energy_net_usd: number;
            /** Annual Ev Charge Kwh */
            annual_ev_charge_kwh: number;
            /** Annual Ev Discharge Kwh */
            annual_ev_discharge_kwh: number;
            /** Annual Gas Co2 Kg */
            annual_gas_co2_kg: number;
            /** Annual Gas Consumption Kwh Th */
            annual_gas_consumption_kwh_th: number;
            /** Annual Gas Cost Usd */
            annual_gas_cost_usd: number;
            /** Annual Heat Produced Kwh */
            annual_heat_produced_kwh: number;
            /** Annual Heating Demand Kwh Th */
            annual_heating_demand_kwh_th: number;
            /** Annual Hp Elec Kwh */
            annual_hp_elec_kwh: number;
            /** Annual Thermal Storage Cycles */
            annual_thermal_storage_cycles: number;
            /** Annual Throughput Cycles */
            annual_throughput_cycles: number;
            /** Battery Eol Year */
            battery_eol_year: number;
            /** Crf */
            crf: number;
            /** Dg Emissions Kg */
            dg_emissions_kg: number;
            /** Dg Fuel Consumption Liters */
            dg_fuel_consumption_liters: number;
            /** Dg Operating Hours */
            dg_operating_hours: number;
            /** Ev V2G Revenue */
            ev_v2g_revenue: number;
            /** Gas Boiler Capex */
            gas_boiler_capex: number;
            /** Gas Boiler Npc */
            gas_boiler_npc: number;
            /** Grid Emissions Kg */
            grid_emissions_kg: number;
            /** Hp Model Name */
            hp_model_name: string;
            /** Initial Investment */
            initial_investment: number;
            /** Kpi Contract Version */
            kpi_contract_version: string;
            /** Lcoe */
            lcoe: number;
            /** Lem */
            lem: number;
            /** Lpsp */
            lpsp: number;
            /** Mean Cop Cooling */
            mean_cop_cooling: number;
            /** Mean Cop Heating */
            mean_cop_heating: number;
            /** Monthly Grid Cost */
            monthly_grid_cost: number[];
            /** Monthly Grid Kwh */
            monthly_grid_kwh: number[];
            /** Npc */
            npc: number;
            /** Operating Cost */
            operating_cost: number;
            /** Peak Demand Kw By Month */
            peak_demand_kw_by_month: number[];
            /** Renewable Fraction */
            renewable_fraction: number;
            /** Thermal Lpsp Cooling */
            thermal_lpsp_cooling: number;
            /** Thermal Lpsp Heating */
            thermal_lpsp_heating: number;
            /** Thermal Storage Capex */
            thermal_storage_capex: number;
            /** Thermal Storage Cooling Kwh Th */
            thermal_storage_cooling_kwh_th: number;
            /** Thermal Storage Heating Kwh Th */
            thermal_storage_heating_kwh_th: number;
            /** Total Battery Charge */
            total_battery_charge: number;
            /** Total Battery Discharge */
            total_battery_discharge: number;
            /** Total Dg Generation */
            total_dg_generation: number;
            /** Total Emissions Kg */
            total_emissions_kg: number;
            /** Total Energy Dump */
            total_energy_dump: number;
            /** Total Fuel Cost */
            total_fuel_cost: number;
            /** Total Grid Bought */
            total_grid_bought: number;
            /** Total Grid Cost Net */
            total_grid_cost_net: number;
            /** Total Grid Sold */
            total_grid_sold: number;
            /** Total Load Served */
            total_load_served: number;
            /** Total Om Cost */
            total_om_cost: number;
            /** Total Pv Generation */
            total_pv_generation: number;
            /** Total Replacement Cost */
            total_replacement_cost: number;
            /** Total Salvage */
            total_salvage: number;
            /** Total Unmet Load */
            total_unmet_load: number;
            /** Total Wt Generation */
            total_wt_generation: number;
        };
        /**
         * SizingRow
         * @description One row of ``sizing.csv`` (the optimiser's chosen component sizing).
         */
        SizingRow: {
            /** Capacity */
            capacity: number;
            /** Capital Cost */
            capital_cost: number;
            /** Component */
            component: string;
            /** Count */
            count: number;
            /** Unit */
            unit: string;
        };
        /**
         * ValidateRequest
         * @description Request body for ''POST /api/v1/validate''.
         *
         *     Attributes
         *     ----------
         *     scenario:
         *         Raw scenario mapping to validate against the SAMBA schema.
         */
        ValidateRequest: {
            /**
             * Scenario
             * @description Scenario mapping with the same structure as a scenario YAML file (schema_version, project, location, load, components, tariff, ...). Validated against the SAMBA Scenario model; see scenario.schema.json for the full shape.
             */
            scenario: {
                [key: string]: unknown;
            };
        };
        /**
         * ValidateResponse
         * @description Response body for ''POST /api/v1/validate''.
         *
         *     Attributes
         *     ----------
         *     valid:
         *         ''True'' when the scenario passes all schema checks.
         *     errors:
         *         List of ''"field.path: message"'' strings describing every validation
         *         failure.  Empty when ''valid is True''.
         */
        ValidateResponse: {
            /**
             * Errors
             * @default []
             */
            errors: string[];
            /** Valid */
            valid: boolean;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    listJobs: {
        parameters: {
            query?: {
                /** @description Filter by status (pending/running/completed/failed) */
                status?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobStatusResponse"][];
                };
            };
            /** @description Bad request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal server error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    submitJob: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["JobSubmitRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobSubmitResponse"];
                };
            };
            /** @description Bad request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal server error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getJob: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobStatusResponse"];
                };
            };
            /** @description Bad request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal server error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    deleteJob: {
        parameters: {
            query?: {
                /** @description Also delete the artifact directory from disk. */
                delete_artifacts?: boolean;
            };
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Bad request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal server error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getArtifact: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
                filename: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Bad request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal server error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    validateScenario: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ValidateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ValidateResponse"];
                };
            };
            /** @description Bad request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Internal server error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    getHealth: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
            /** @description Internal server error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
}
