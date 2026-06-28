# SAMBA Architecture Debt Review (Post-Remediation)

Date: 2026-03-04  
Scope: `samba/`, `samba_cli/`, `samba_service/`, `tests/`, `docs/`

## Executive summary

All previously logged priority debt items were addressed in code.  
The codebase is now materially cleaner for the next phase (numerical alignment + deeper testing).

## Baseline items and closure status

1. **Service depended on CLI resolver internals** — **Resolved**
   - Service, CLI, scripts, and tests now import the core resolver from
     `samba/input_resolver.py` directly.
   - The `samba_cli/resolver.py` compatibility shim has been removed.

2. **`compile_energy_system()` god function** — **Resolved**
   - Refactored into staged orchestration helpers in `samba/compiler/compiler.py`.

3. **`build_economics()` / `compute_kpis()` god functions** — **Resolved**
   - Economics split into replacement/O&M/gas/salvage helpers in `samba/economics/cashflow.py`.
   - KPI assembly now uses focused stat helpers in `samba/run_result/kpis.py`.

4. **`RunResult.metadata` inconsistent with on-disk metadata** — **Resolved**
   - Pipeline now builds/returns metadata consistently for both disk and in-memory runs in `samba/_pipeline.py`.

5. **Empty/dead package shells (`samba/components`, `samba/util`)** — **Resolved**
   - Package `__init__.py` stubs removed.

6. **Unused `ComponentBuilder` protocol (`builders/base.py`)** — **Resolved**
   - Dead protocol file removed.

7. **Extractor layer still concentrated in one large module** — **Resolved**
   - Extractors split into domain modules:
     - `samba/solver/component_extractors/electrical.py`
     - `samba/solver/component_extractors/thermal.py`
   - Old `samba/solver/_component_extractors.py` removed.

8. **Service typing debt (`_job_to_response` + `type: ignore`)** — **Resolved**
   - Correct `Job` typing applied in `samba_service/app.py`.
   - `type: ignore[arg-type]` call-site suppressions removed.

9. **Architecture docs drift** — **Resolved**
   - `docs/developer/architecture.md` updated to current package layout and boundaries.

10. **Brittle extractor tests keyed on private class names** — **Resolved**
    - Added stable extractor key registry (`_EXTRACTOR_REGISTRY`) in `samba/solver/extract.py`.
    - Tests now select extractors by stable keys in `tests/unit/test_extractor_protocol.py`.

11. **Run directory collision risk** — **Resolved**
    - Collision-safe run directory creation added in `samba/run_result/writer.py`.

12. **CLI command handlers as god-file hotspot** — **Resolved**
    - `samba_cli/main.py` reduced to Typer wiring.
    - Command logic moved into `samba_cli/handlers.py`.

## Current risk posture

- **High-priority architecture debt:** none open from the tracked list.
- **Primary next risk:** numerical parity and regression confidence, not structure.

## Recommended next phase

1. Expand focused regression tests around:
   - KPI/economics helper boundaries
   - metadata + artifact invariants
   - extractor registry contract keys
2. Begin parity runs against prior implementation outputs and document expected/acceptable deltas.
