# Changelog

All notable changes to SAMBA are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Releases from 5.3.1 (the first published to PyPI) are tagged in this repository and
linked at the foot of this file; earlier versions predate its reinitialization and
are listed for history without comparison links.

## [Unreleased]

_Nothing yet._

## [5.3.1] - 2026-06-28

Maintenance release: first publication to PyPI, dependency updates, and CI
hardening. No functional or API changes.

### Added

- **Published to PyPI** — `pip install samba-core` (via OIDC Trusted Publishing).

### Changed

- **UI dependencies** updated to current majors: Vite 8 (rolldown bundler),
  `@vitejs/plugin-vue` 6, vue-tsc 3, TypeScript 6, vue-router 5, js-yaml 5,
  jsdom 29 — plus a non-major batch and lock-file maintenance that clears all
  npm audit findings.
- **CI** unified on the `just` recipes (`just check` / `just ui-check` / `just test`)
  so the pipeline matches local exactly, restoring the schema-export drift gate
  that the inlined workflow had omitted. GitHub Actions updated to current majors.

### Removed

- Unused `lucide-vue-next` dependency.
- `@types/js-yaml` — js-yaml 5 ships its own type declarations.

## 5.3.0 - 2026-06-14

Schema-first cutover: the backend Pydantic models become the single source of
truth for every shape that crosses to the UI, the UI's TypeScript types are
generated from them, and drift gates on both sides make divergence a build
failure. This eliminates the class of bug where the web UI's hand-written type
copies silently disagreed with the backend (empty KPI cards, zeroed economics,
and a scenario editor whose every fresh scenario was invalid). Backwards-compatible
for the Python API and scenario schema.

### Added

- **JSON Schema export pipeline** (`scripts/export_schemas.py` + `just schemas`):
  emits `schemas/*.schema.json` for the scenario, run-result artifacts, and
  service envelope from the Pydantic models. A drift test
  (`tests/unit/test_schema_export.py`) and `just check` fail if the committed
  schemas are stale.
- **Artifact contracts** (`samba/run_result/contracts.py`): Pydantic models
  (`KpiSummary`, `EconomicsReport`/`CashflowYear`, `SizingRow`, `DispatchContract`)
  formalizing the previously dict-only run-result outputs, validated against real
  solver output (`tests/integration/test_artifact_contracts.py`).
- **`solve_time_s`** on the job status API (`GET /api/v1/jobs/{run_id}`),
  populated from the run's wall-clock solve time.
- **UI type generation** (`ui: npm run gen:types`, `just ui-check`): TypeScript in
  `ui/src/api/generated/` is generated from `schemas/` via
  `json-schema-to-typescript`, with its own drift gate.

### Changed

- The scenario JSON Schema is now generated (`schemas/scenario.schema.json`,
  replacing the hand-committed `scenario-v2.0.json`).
- **Web UI rebuilt on the generated schema**: the results dashboard binds to the
  real KPI / economics / sizing contracts; the scenario editor is built on the
  generated `Scenario` type with a schema-valid default (a fresh scenario now
  validates with zero errors and is runnable). UI envelope types
  (`JobRecord`/`ValidationResponse`) are generated; no hand-written contract
  copies remain.

## 5.2.0 - 2026-06-14

Polishes the data-driven heat-pump COP as an explicit **opt-in**, keeping the
license-clean first-principles physics model as the shipped default (resolving the
post-v5 "NEEP COP dataset promotion" question by deciding _not_ to promote).
Backwards-compatible; no behaviour change to existing scenarios.

### Added

- `examples/grid_pv_heat_pump_dataset.yaml` — a runnable demo of the opt-in
  `cop_source: "dataset"` COP path, fitting the committed representative reference
  CSV with a degree-day thermal load so the heat pump actually dispatches. Locked
  by `tests/integration/test_cop_dataset_example.py`.

### Changed

- Documented all three heat-pump `cop_source` modes (physics default, dataset
  opt-in, NEEP local-only workflow) in `docs/thermal-components.md`, and clarified
  that `catalog` selects the physics model — not a vendor catalog.
- Strengthened `samba fetch-cop-data` messaging (CLI, module docstring, curated-CSV
  provenance header): fetched third-party performance data is **local-only** and
  must not be committed or redistributed without confirmed rights.
- Tightened the provenance-guard `_reference` marker to the vendored
  reference-tree path (`_reference/`) so legitimate filenames (e.g.
  `cop_ashp_reference.csv`) no longer trip it.

## 5.1.0 - 2026-06-14

Post-independence follow-ups: a data-driven heat-pump COP option, a CLI/service
thermal-resolution fix, and a documentation accuracy pass. Backwards-compatible.

### Added

- **Data-driven heat-pump COP** (`heat_pump.cop_source: "dataset"` +
  `cop_dataset_path`): fits COP(T) curves from a performance-dataset CSV
  (`outdoor_temp_c,cop_heating,cop_cooling`), as an alternative to the built-in
  physics model. `samba fetch-cop-data` sources and normalises such a dataset
  (NEEP cold-climate ASHP default mapping, EER→COP, per-temperature median,
  provenance header; output git-ignored pending a license check). A
  representative, license-clean `examples/content/cop_ashp_reference.csv` ships
  in-tree for tests/examples.
- `.markdownlint.json` + `.markdownlintignore` for consistent docs linting.

### Fixed

- **Degree-day thermal demand read as zero on the `samba run` CLI** (and the REST
  service and pareto sweeps): `scenario_dir` was not threaded to `samba.run`, so
  weather fell back to a stub. Weather and thermal/HP CSV paths now resolve
  relative to the scenario; regression test added.

### Changed

- Documentation accuracy pass: rewrote `known-limitations.md` to the shipped v5
  reality; repositioned `about.md` / `index.md` from a pre-build proposal to the
  shipped product; corrected the heat-pump schema and examples in
  `scenario-reference.md` / `thermal-components.md`.
- CHANGELOG reworked to a complete Keep a Changelog (Unreleased section, version
  comparison links, retroactive v1.0.0 / v2.0.0 tags).
- Added a publication-readiness audit + post-v5 roadmap (internal planning);
  MPL-2.0 headers on all scripts (106/106).

## 5.0.0 - 2026-06-13

**Independent.** SAMBA is now a fully independent MPL-2.0 codebase with its own
models, data, and constants ([Acknowledgements](docs/acknowledgements.md)). This is
primarily a provenance/licensing milestone rather than a feature release — there are
**no breaking public API changes** — but several physical models were re-sourced from
primary authorities, which shifts golden KPI baselines, so it is a major version bump.

### Added

- **Provenance guard** (`tests/unit/test_provenance_guard.py`): fails CI if
  upstream-provenance markers reappear in production code, scripts, or shipped
  config, or if the `_reference/` tree is re-tracked. Locks the decoupling in
  permanently.
- **`.env` support for NSRDB credentials:** committed `.env.example`; the CLI now
  auto-loads a local `.env` (dependency-free; never overrides existing shell variables)
  so `NREL_API_KEY` / `NREL_API_EMAIL` need not be exported manually.
- **Sample-data generator** (`scripts/generate_sample_data.py`): regenerates the bundled
  synthetic residential load profile deterministically.

### Changed

- **Solar position + plane-of-array re-sourced to [pvlib](https://pvlib-python.readthedocs.io)**
  (BSD-3): NREL SPA solar position + isotropic (Liu & Jordan) transposition replace the
  previous in-house implementation. Adds a `pvlib` runtime dependency. The NOCT
  cell-temperature, per-kWp power, and bifacial models are unchanged.
- **KiBaM battery re-derived** from the primary source — Manwell & McGowan (1993),
  _Solar Energy_ 50(5) — using the published notation, with an inline citation.
- **Heat-pump COP re-sourced** to a physics-based Carnot-fraction model (Carnot limit ×
  a practical second-law efficiency, per ASHRAE _Fundamentals_) with a Stull (2011)
  wet-bulb approximation, replacing the prior manufacturer-regression coefficient tables
  and psychrometric constants. Catalog model labels are now generic (e.g. `ASHP-3ton`).
  COP is modelled as size-independent; catalog fidelity drops relative to the prior
  catalog-regression baseline. The `COPArrays` / `build_cop_arrays` /
  `select_catalog_model` public interface is preserved (compiler and HP builder unchanged).
- **NSRDB weather fetch endpoint corrected and upgraded:** host is `developer.nlr.gov`
  (NLR Developer Network) and the request now targets the PSM4 GOES v4 aggregated
  endpoint (the older PSM3 endpoint is deprecated; coverage 2018+).
- **Input data re-homed:** clean NSRDB weather (`examples/content/weather_sf_2019.csv`,
  US-government public domain) and a synthetic load profile
  (`examples/content/load_residential_8760.csv`) replace the previous bundled data; the
  `generic_*` load sources now use an algorithmic shape generator instead of a data file.
- **Tariff, load, and EV internals re-expressed independently** as part of the
  decoupling: tariff rate-array builders, the load expander/generic shape, and the EV
  presence-schedule builder were restructured and all upstream-provenance markers removed.
- **All 22 golden references re-baselined** as pure-SAMBA regression baselines against the
  re-sourced models (`reference.json` KPI values updated; tolerances and structure kept).
- **Documentation repositioned:** README / `docs/about.md` / `docs/index.md` frame SAMBA
  as an independent project ([Acknowledgements](docs/acknowledgements.md)). Removed
  "successor" / "port" / "clean-room reimplementation" wording and the feature-by-feature
  comparison framing.

### Removed

- The git-tracked vendored reference tree (`_reference/`, ~300 MB / 105 files) is
  untracked and git-ignored (a local copy may be kept outside version control).
- `docs/developer/legacy-parity.md` (a feature-by-feature legacy mapping).
- Stale parity-diagnostic scripts that read the now-removed `_reference/` tree
  (`scripts/diag_kpi_delta.*`, `scripts/diag_model_deep.*`).

## 4.0.0 - 2026-06-13

**Real-World Readiness.** Closes real-world modelling and deployment gaps.
Backwards-compatible: existing v1–v3 scenarios
run unchanged; all new behaviour is opt-in. `schema_version: "4.0"` accepted.

### Added

- **Demand charges** (`tariff.demand_charge`): `$/kW-month` on the monthly peak
  grid import, modelled in the LP so the solver shaves peaks. KPIs
  `annual_demand_charge_usd`, `peak_demand_kw_by_month`.
- **NEM reconciliation** (`tariff.nem`): monthly `$0`-floored bills with export
  credit carryover and year-end settlement. KPI `annual_energy_net_usd`.
- **Epsilon-constraint Pareto** (`constraints.max_total_emissions_kg`,
  `samba pareto --method epsilon`): traces non-convex frontier regions the
  weighted-sum method misses.
- **Battery degradation** (`battery.degradation`): throughput + calendar capacity
  fade derives an effective lifetime driving replacement economics. KPIs
  `annual_throughput_cycles`, `battery_eol_year`.
- **Bifacial PV** (`pv.module_type: bifacial`, `pv.bifaciality`): rear-side
  ground-reflected gain.
- **NSRDB weather fetch** (`weather.source: nsrdb`, `samba fetch-weather`):
  NREL API fetch with on-disk caching; offline-repeatable.
- **Load templates** (`load.source: template`): built-in residential / commercial
  / industrial shapes scaled to an annual total.
- **Persistent job store** (`SAMBA_PERSIST_JOBS`): SQLite-backed REST job store so
  jobs survive a restart. **Docker image** + `docs/deployment.md`.
- **Golden scenarios** g20 (demand charge), g21 (NEM net-billing), g22 (bifacial),
  plus a runnable `examples/commercial_demand_nem.yaml`.

### Changed

- KPI contract → `2.1` (additive; new fields above).
- Version is now single-sourced from `samba/_version.py` (hatchling dynamic).

## 3.0.1 - 2026-06-13

Maintenance release: tooling, test coverage, documentation, and example fixes.
Resolves all outstanding items from the v2.0.0 pre-v3 audit. No breaking changes.

### Added

- `SolverConfig.strict_kibam` (default `False`): when `True`, KiBaM post-solve
  dispatch violations raise `ConstraintViolationError` instead of logging a warning.
- `RunResult.scenario`: lazy, cached, typed `Scenario` accessor over `scenario_raw`.
- Full-year (8760-h) MILP unit-commitment regression tests (`TestMILPFullYear`),
  closing audit C1 — the 8760-h DG MILP solves correctly under oemof-solph 0.6.4.
- Two-tier golden KPI contract: scalar `kpis` (tolerance-checked) vs list-valued
  `series_kpis`, enforced by `test_reference_json_valid`.

### Changed

- **Tooling cut over to [uv](https://docs.astral.sh/uv/):** PEP 735 `dev`
  dependency group, committed `uv.lock`, `justfile`, uv-based CI workflows;
  `requirements-dev.lock` removed.
- Reworked the README/about attribution; added a license/provenance audit
  (internal planning).
- Documented current-release caveats (KiBaM LP relaxation, DG fuel-curve intercept,
  weighted-sum Pareto, in-memory REST job store) in `docs/known-limitations.md`.
- Completed PyPI classifiers (audience, OS, development status).

### Fixed

- **Example scenarios now run out of the box.** All three `examples/*.yaml`
  referenced non-existent data files and used stale pre-v2/v3 schema fields; they
  now point at the bundled `examples/content/` data and the current schema.
- Replaced the last production `assert` guard with an explicit `ValueError`; ruff
  rule `S101` now bans `assert` in production code (audit C2).
- Added MPL-2.0 license headers to the `samba_service` modules that lacked them.

## 3.0.0 - 2026-03-04

**Thermal Domain + Building Analysis.** `schema_version: "3.0"` for thermal scenarios;
all v1/v2 scenarios remain valid.

### Added

- **Thermal domain:** heating bus and cooling bus with full oemof-solph topology.
- **Heat pump component** (air-source, `components.heat_pump`): catalog-based automatic
  sizing; temperature-dependent COP model with outdoor dry-bulb temperature for
  heating and indoor wet-bulb temperature for cooling.
  Modes: `heating_only`, `cooling_only`, `both`.
  Regression-tested in golden g19. (COP model re-sourced to a physics-based
  formulation in 5.0.0.)
- **Thermal storage** (hot-water buffer, `components.thermal_storage`): investment
  optimisation for tank capacity; configurable charge/discharge efficiency and standby
  loss rate.
- **Building thermal loads** (`load.thermal`): hourly CSV or degree-day model
  (UA × ΔT from weather file); configurable heating/cooling setpoints.
- **Natural gas supply** (`components.gas_supply`): boiler/furnace with flat, seasonal,
  and tiered gas rate structures; LHV-basis CO₂ accounting.
- **HP vs gas boiler merit-order dispatch:** LP selects hour-by-hour lowest-cost
  thermal source given electricity and gas prices.
- **Thermal LPSP** (`thermal_lpsp_heating`, `thermal_lpsp_cooling`): loss-of-load
  probability for thermal demand; `constraints.thermal_lpsp_max` constraint.
- **Seven v3 golden scenarios** (g13–g19) covering all new thermal features with locked
  KPI references and semantic invariant tests (`tests/goldens/test_v3_goldens.py`).
- `docs/thermal-components.md` — thermal domain guide (COP equations, degree-day
  model, gas unit conversions, HP vs gas economics).
- New thermal KPIs: `mean_cop_heating`, `mean_cop_cooling`, `annual_heat_produced_kwh`,
  `annual_cool_produced_kwh`, `annual_hp_elec_kwh`, `annual_heating_demand_kwh_th`,
  `annual_cooling_demand_kwh_th`, `thermal_storage_capex`, `annual_thermal_storage_cycles`,
  `annual_gas_consumption_kwh_th`, `annual_gas_cost_usd`, `annual_gas_co2_kg`,
  `gas_boiler_npc`, `gas_boiler_capex`.

### Changed

- `schema_version: "2.0"` accepted by validator (all v1/v2 scenarios remain valid).
  Added `"3.0"` to `_KNOWN_SCHEMA_VERSIONS` for new thermal scenarios.
- `scenario_dir` argument added to `samba.run()` for CSV thermal load path resolution;
  auto-detected from scenario file path when loading from disk.
- `docs/scenario-reference.md` updated with v3 schema additions.
- `README.md` updated with v3 feature table and thermal-components documentation link.

### Fixed

- Thermal CSV load paths now correctly resolved relative to the scenario YAML file
  location (no longer required to run from the scenario directory).
- Weather auto-loaded for heat-pump scenarios that do not include PV (previously
  weather was only resolved when PV/wind was enabled).

## 2.0.0 - 2026-03-03

**Extended Electrical.** `schema_version: "1.1"` (backwards-compatible with `"1.0"`).

### Added

- **Multi-objective optimisation** (`objective.type: cost_and_emissions`): `emissions_weight`
  ($/kg CO₂) added to NPC in the LP objective function; `co2_per_liter_kg` on DG component.
- **Diesel Generator economics** (Phase 14): `startup_cost`, `min_up_hours`, `min_down_hours`
  fields on `diesel_generator`; LP relaxation used for annual runs (MILP at 168-h horizon
  via `test_dg_milp.py`); `dg_operating_hours` KPI added.
- **EV smart charging** (Phase 15): `electric_vehicle` component with `capacity_kwh`,
  `max_charge_kw`, `arrival_hour`, `departure_hour`, `workdays_per_week`, `v2g_enabled`,
  `max_discharge_kw`; `annual_ev_charge_kwh`, `annual_ev_discharge_kwh`, `ev_v2g_revenue` KPIs.
- **KiBaM battery chemistry** (Phase 16): `battery.chemistry: kibam` enables kinetic battery
  model (c-rate, Q1/Q2 charge partitioning, `soc_min` depth-of-discharge enforcement).
- **Endogenous tiered tariff** (Phase 17): `tariff.buy.endogenous_tiering: true` on tiered
  buy rates enforces monthly consumption against tier limits inside the LP.
- **Six v2 golden scenarios** (g07–g12) covering all new features with locked KPI references
  and semantic invariant tests (`tests/goldens/test_v2_goldens.py`).
- `total_emissions_kg`, `monthly_grid_kwh`, `total_grid_cost_net` KPIs in solver output.

### Changed

- `schema_version: "1.1"` accepted by validator (backwards-compatible with `"1.0"`).
- Golden scenario glob updated to `g[0-9]*` to cover two-digit indices g10–g12.

### Notes

- MILP unit-commitment (`min_up_hours > 0`) is only tested at 168-h horizon due to
  oemof-solph/Pyomo NonConvexFlowBlock interaction at 8760-h scale (see `test_dg_milp.py`).
  _(Superseded 2026-06-13: the 8760-h MILP solves correctly under oemof-solph 0.6.4;
  full-year unit-commitment regression added as `TestMILPFullYear`. See audit item C1.)_
- KiBaM LP relaxation may produce up to ~10 timestep Q1 SOC violations; a post-validation
  warning is emitted; LPSP remains 0.

## 1.0.0 - 2026-03-03

**Electrical Core.** First release: end-to-end LP microgrid optimisation.

### Added

- End-to-end microgrid optimisation via LP (oemof-solph + HiGHS).
- Scenario validation: Pydantic v2 schema, all 8 tariff buy-rate structures, 3 sell-rate types.
- POA irradiance model (HDKR transposition) from NSRDB-format CSV weather files.
- Load profile expansion: hourly CSV, daily profile, monthly peak, generic annual/monthly total.
- Component builders: PV (HDKR + cell temp model), Battery (Li-ion), Wind Turbine (power curve),
  Diesel Generator (fuel curve), Inverter (DC/AC), Grid (buy + export).
- Investment optimisation (null capacity → design variable solved by LP).
- Economics post-processing: NPC, LCOE, CRF, O&M, replacement scheduling, salvage, grid escalation.
- Grid price escalation (`grid_escalation_rate`) with escalated present-worth factor.
- Monthly sell rate type (`sell.type: monthly`) with 12-value array.
- `annual_kwh` field on Load for `generic_annual_total` source.
- CLI: `samba run`, `samba validate`, `samba info` (Typer + Rich).
- Artifact outputs: `dispatch.parquet`, `dispatch.csv`, `kpis.json`, `sizing.csv`,
  `economics.json`, `metadata.json`, `tariff.parquet`, `scenario.yaml`.
- 6 golden benchmark scenarios (g01–g06).
- 293 unit, integration, and golden benchmark tests.
- Full documentation: Getting Started, Scenario Reference, CLI Reference, API Reference,
  Known Limitations, Developer Architecture, Developer Results Contract.

### Notes

- Single-objective NPC minimisation only (v1 scope); emissions reported but not optimised.
- NEM annual-reconciliation (bill flooring) deferred to v2.
- Electrical loads only; thermal and EV deferred to v2/v3.
- DG binary on/off constraints require MILP (v2); v1 uses LP relaxation.

[Unreleased]: https://github.com/sambaenergies/samba/compare/v5.3.1...HEAD
[5.3.1]: https://github.com/sambaenergies/samba/releases/tag/v5.3.1
