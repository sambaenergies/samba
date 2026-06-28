# Developer: Architecture

This document describes the current SAMBA package structure and layer boundaries.

## Package Layout

```text
samba/                          # Core library
  __init__.py                   # Public API (run, run_many, read_results, __version__)
  _pipeline.py                  # Internal orchestration for run()
  input_resolver.py             # Scenario -> load/pv/wind arrays (shared by CLI/service)
  scenario/                     # Pydantic models + YAML loader
  weather/                      # NSRDB parsing + irradiance/cell temperature models
  load_profiles/                # Electrical/thermal/EV load profile builders
  tariff/                       # Tariff model -> hourly arrays
  compiler/
    compiler.py                 # Scenario + arrays -> oemof EnergySystem
    builders/                   # Component builders (pv, wind, grid, diesel, thermal, EV)
  batteries/                    # Battery chemistry implementations (li-ion, KiBaM)
  solver/
    runner.py                   # Solve wrapper + solver error mapping
    extract.py                  # DispatchResult assembly and extraction orchestration
    component_extractors/       # Domain extractors (electrical, thermal)
  economics/                    # NPC, cashflow, emissions, salvage, replacement
  run_result/                   # KPI assembly + artifact writer/reader
  pareto/                       # Multi-point weighted-sum Pareto sweep

samba_cli/                      # CLI adapter
  main.py                       # Typer wiring (command signatures/options)
  handlers.py                   # Command implementations (run/validate/info/serve/pareto)
  resolver.py                   # Backward import shim -> samba.input_resolver.resolve_arrays
  formatting.py                 # Rich output helpers

samba_service/                  # FastAPI service adapter
  app.py                        # HTTP routes + response mapping
  jobs.py                       # Async job execution + in-memory job store
  config.py                     # Environment/config model
  auth.py                       # API-key dependency
  models.py                     # Request/response models

tests/
  unit/                         # Fast tests, no real solver loop
  integration/                  # End-to-end behavior tests
  goldens/                      # Golden scenario parity checks
```

## Layer Boundaries

```text
scenario          <- standalone domain model
weather           <- scenario
load_profiles     <- scenario
tariff            <- scenario
compiler          <- scenario, weather, load_profiles, tariff, batteries
solver            <- compiler
economics         <- solver, scenario, tariff
run_result        <- economics, solver, scenario
pipeline/public   <- orchestrates all core layers
cli/service       <- adapter layers over core modules
```

Rules:

1. Core modules in `samba/` must not import from `samba_cli/` or `samba_service/`.
2. Adapter code may import core modules, but adapter-specific concerns stay in adapters.
3. Scenario validation occurs before compilation/solve.
4. Artifact schema changes must stay synchronized with `run_result/` writer+reader and tests.

## Current Design Notes

### Compiler orchestration

`compile_energy_system()` is a staged orchestrator:

- build time index
- add DC-side components
- add AC-side components
- add thermal domain, heat pump, storage, gas supply
- add unmet/dump penalties

Each stage is a focused helper with narrow inputs.

### Result extraction and KPIs

- `solver/extract.py` owns extraction orchestration and dispatch DataFrame contract.
- `solver/component_extractors/` contains per-domain extractor implementations.
- `run_result/kpis.py` composes helper-level statistics into final KPI/economics payloads.

### Metadata and artifacts

- `run_result/writer.py` provides `build_metadata()` and write functions.
- Pipeline returns in-memory metadata consistent with what is written on disk.
- Run directory creation handles timestamp collisions safely.

### CLI/service adapters

- `samba_cli/main.py` is intentionally thin; command logic is in `samba_cli/handlers.py`.
- Service jobs resolve arrays via `samba.input_resolver`, not CLI internals.
