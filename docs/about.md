# SAMBA — Executive Summary

## What This Is

SAMBA (**S**ystems **A**dvisor for **M**icrogrids & **B**uilding **A**nalysis) is an independent, MPL-2.0 tool that sizes and dispatches hybrid microgrids (solar, wind, battery, diesel, grid) to minimize lifetime cost. It is a self-contained codebase with its own models, data, and architecture (see [Acknowledgements](acknowledgements.md)).

SAMBA is built around **oemof-solph**, an established open-source energy system modeling framework backed by **Pyomo** mathematical programming (LP/MILP). Rather than simulating thousands of random candidate solutions and scoring each one, SAMBA compiles the microgrid design problem into a single mathematical program and solves it optimally.

SAMBA is a reproducible microgrid and building energy system optimization platform. It prioritizes transparency, reproducibility, and extensibility over maximal physical fidelity — models are formulated to remain computationally tractable while preserving system-level decision accuracy.

## Design Rationale

SAMBA is built on a few deliberate choices:

- **Optimality** — An LP/MILP formulation enables deterministic optimization and yields solutions that are optimal with respect to the formulated model, subject to solver tolerances (no run-to-run variation from metaheuristics).
- **Performance** — A single solve (seconds) replaces thousands of dispatch simulations (minutes–hours).
- **Maintainability** — A modular, layered architecture with full test coverage.
- **Extensibility** — Adding a component means writing one builder function.
- **Reproducibility** — Every input and output is pinpointed: YAML in, versioned artifact directory out.

## Scope

SAMBA was built up in phased releases to avoid half-modelled features; all of the
following are shipped as of v5.0.0. See the [CHANGELOG](../CHANGELOG.md) for the
per-version history.

**Electrical core:**

- Components: PV, wind turbine, Li-ion battery, diesel generator, bidirectional inverter, grid connection
- 8 electricity rate structures; full lifetime economics (NPC, LCOE, replacement, salvage, grid cost projection — computed in post-processing from the optimised annual dispatch)
- Python API + CLI + REST service adapter

**Extended electrical:**

- Multi-objective optimisation (NPC + emissions; weighted-sum and epsilon-constraint Pareto)
- EV / V2G, KiBaM battery, diesel unit commitment (min up/down, start costs)
- Endogenous tiered tariffs solved in-model
- Demand charges, NEM/net-billing reconciliation, battery degradation, bifacial PV, NSRDB weather fetch, load-profile templates
- Async REST service with an optional SQLite-persistent job store + Docker image

**Thermal domain + building analysis:**

- Air-source heat pump (physics-based COP), thermal storage, building heating/cooling loads
- Thermal buses (heating + cooling), natural gas rates, gas boiler/furnace
- HP vs gas merit-order dispatch

## Architecture

Three layers, three packages:

1. **samba** core library (MPL-2.0) — Scenario loading → model compilation → solve → post-processing
2. **samba-cli** — Typer-based CLI: `samba run scenario.yaml -o results/`
3. **samba-service** — FastAPI REST wrapper (async jobs, optional persistent store), backend for a native app + web UI

4. **UI** (`/ui/` directory) — a Vue 3 + Vite + **Tauri** front-end that runs in the browser (web mode) or as a native desktop app. Its TypeScript types are **generated from the backend Pydantic models** (JSON Schema → TS, drift-gated), so the UI and API contracts stay in lock-step. It communicates only via the REST API, so it could be extracted into a standalone `samba-ui` repository with no architectural changes.

The core uses a **compiler pattern**: a validated YAML scenario is compiled into an oemof energy system model, solved, then post-processed into a standardized artifact directory.

## Engineering Gates

Each release is held to four quality gates:

| Gate  | After         | What Must Be True                                                               |
| ----- | ------------- | ------------------------------------------------------------------------------- |
| **A** | Schema design | Scenario schema v1.0 frozen, results contract frozen, versioning policy defined |
| **B** | First solve   | `samba run example.yaml` works, energy balance checks pass                      |
| **C** | Benchmarks    | Golden scenarios in CI, tolerances defined, results diffable                    |
| **D** | Release       | Install guide, quickstart, results interpretation, known limitations documented |

## Release history

The electrical core (v1), extended electrical features (v2), thermal domain (v3),
real-world-readiness features (v4), and the independence/relicensing milestone (v5)
have all shipped. The [CHANGELOG](../CHANGELOG.md) records each release in detail.

## Validation Strategy

Golden scenarios (grid-tied TOU, off-grid, wind+grid, tiered rate, seasonal tiered,
thermal) are solved by SAMBA and pinned as regression baselines. Each must satisfy:

- Energy balance satisfied (supply = demand + losses at every timestep)
- Reliability constraints satisfied (LPSP ≤ target)
- KPI agreement with the pinned baseline within tolerance: LCOE ±10%, component sizing ±20%, generation/consumption ±5%
- All deviations explainable by physical or formulation reasoning

Baselines are re-captured whenever a model is intentionally changed, with the reason
recorded.

## Deliverable

A PyPI package (`samba-core`) with:

- `pip install samba-core[cli]`
- `samba run scenario.yaml` produces a complete, reproducible results directory
- Full documentation: installation, quickstart, results interpretation, known limitations
- 22 golden scenarios passing in CI (electrical, EV, thermal, demand-charge/NEM, bifacial)
