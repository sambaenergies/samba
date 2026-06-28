# API Reference

This page documents the public Python API. All symbols listed here are part of the
**stable public interface** (current release v5.3.0). Internal functions and classes
(those not listed here) may change without notice.

---

## `samba.run()`

```python
samba.run(
    scenario_or_path: Scenario | Path | str,
    *,
    load_kw: np.ndarray,
    output_dir: Path | str | None = None,
    config: SolverConfig | None = None,
    pv_per_kwp: np.ndarray | None = None,
    tariff_arrays: TariffArrays | None = None,
    wind_power_kw: np.ndarray | None = None,
) -> RunResult
```

Run the full SAMBA pipeline and return a `RunResult`.

**Executes:**

1. Load / validate the scenario (if a path is supplied)
2. Resolve tariff arrays from the scenario (unless pre-supplied)
3. Compile the `oemof.solph.EnergySystem`
4. Solve the LP with the configured solver
5. Extract dispatch and optimal capacities
6. Compute KPIs, economics, sizing
7. Write all result artifacts to `output_dir` (if supplied)
8. Return a `RunResult` with all data in memory

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `scenario_or_path` | `Scenario \| Path \| str` | A validated `Scenario` or a path to a YAML file. |
| `load_kw` | `np.ndarray` shape `(8760,)` | Hourly electrical demand [kW]. **Required.** |
| `output_dir` | `Path \| str \| None` | Write artifact directory here. `None` = in-memory only. |
| `config` | `SolverConfig \| None` | Solver options. Defaults to `SolverConfig()`. |
| `pv_per_kwp` | `np.ndarray \| None` shape `(8760,)` | Normalised PV output [0–1 per kWp]. Required if scenario has PV. |
| `tariff_arrays` | `TariffArrays \| None` | Pre-resolved tariff arrays. Derived from `scenario.tariff` when `None`. |
| `wind_power_kw` | `np.ndarray \| None` shape `(8760,)` | Per-turbine hourly wind power [kW]. Required if scenario has a wind turbine. |

**Returns:** `RunResult`

**Raises:**

| Exception | Condition |
|---|---|
| `FileNotFoundError` | `scenario_or_path` does not exist |
| `ScenarioValidationError` | YAML fails schema validation |
| `SolverNotFoundError` | Configured solver is not installed |
| `InfeasibleError` | LP problem is infeasible |
| `SolverTimeLimitError` | Solver hit the time limit without finding a solution |

---

## `samba.scenario.load_scenario()`

```python
from samba.scenario import load_scenario

scenario = load_scenario(path: Path | str) -> Scenario
```

Load and validate a YAML scenario file.

- Resolves the YAML to a `Scenario` Pydantic model.
- Applies all field defaults.
- Validates cross-field constraints (e.g., TOU periods cover full 24h, battery SOC ordering).
- Raises `ScenarioValidationError` (a subclass of `ValueError`) on any error.

---

## `samba.scenario.ScenarioValidationError`

```python
from samba.scenario import ScenarioValidationError
```

Raised when a scenario fails validation. Inherits from `ValueError`.

Attributes:

- `messages: list[str]` — one error string per failing field, including the JSON path
  (e.g., `"components.pv.derating_factor: value must be in [0, 1]"`)

---

## `samba.solver.runner.SolverConfig`

```python
from samba.solver.runner import SolverConfig

config = SolverConfig(
    solver_name: str = "appsi_highs",
    time_limit_s: int = 600,
    output_verbose: bool = False,
)
```

Solver configuration. Pass to `samba.run(config=...)`.

| Field | Default | Description |
|---|---|---|
| `solver_name` | `"appsi_highs"` | Solver name passed to oemof. Use `"cbc"` for CBC. |
| `time_limit_s` | `600` | Maximum solver time in seconds. |
| `output_verbose` | `False` | Stream solver log to terminal. |

---

## `RunResult`

```python
from samba.run_result.reader import RunResult
```

Returned by `samba.run()`. All result data available in memory.

| Attribute | Type | Description |
|---|---|---|
| `kpis` | `dict[str, float]` | Key performance indicators. See KPI keys below. |
| `sizing` | `pd.DataFrame` | Component sizing table. Columns: `component`, `capacity`, `unit`. |
| `dispatch` | `pd.DataFrame` | 8760-row hourly dispatch. One column per flow. |
| `economics` | `dict[str, Any]` | Full economic breakdown. See [results contract](developer/results-contract.md). |
| `run_dir` | `Path` | Path to the written artifact directory (`Path(".")` when no `output_dir`). |

### KPI Keys

| Key | Unit | Description |
|---|---|---|
| `npc` | `$` | Net Present Cost |
| `lcoe` | `$/kWh` | Levelised Cost of Energy |
| `renewable_fraction` | `[0–1]` | Fraction of load met by renewable generation |
| `lpsp` | `[0–1]` | Loss of Power Supply Probability |
| `total_pv_generation` | `kWh` | Annual PV generation |
| `dg_fuel_consumption_liters` | `L` | Annual diesel fuel consumption |
| `grid_annual_bought_kwh` | `kWh` | Annual energy purchased from grid |
| `grid_annual_sold_kwh` | `kWh` | Annual energy exported to grid |

---

## `samba.input_resolver.resolve_arrays()`

```python
from samba.input_resolver import resolve_arrays

load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(
    scenario: Scenario,
    base_dir: Path,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]
```

Resolve all pre-processing arrays from a validated `Scenario`.

- `load_kw` — 8760-element load profile [kW] from the load source specified in the scenario.
- `pv_per_kwp` — 8760-element normalised PV output [0–1 per kWp], or `None` if no PV.
- `wind_power_kw` — 8760-element per-turbine wind power [kW], or `None` if no wind turbine.

`base_dir` is the directory against which relative CSV paths in the scenario are resolved
(typically `scenario_yaml_path.parent`).

---

## Exception Hierarchy

```
RuntimeError
└── SolverError                          # samba.solver.runner
    ├── SolverNotFoundError              # Solver binary/package not installed
    ├── InfeasibleError                  # LP problem has no feasible solution
    └── SolverTimeLimitError             # Solver hit time limit

ValueError
└── ScenarioValidationError              # samba.scenario
```

---

## Version

```python
import samba
print(samba.__version__)  # "1.0.0"
```
