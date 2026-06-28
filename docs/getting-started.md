# Getting Started

## Prerequisites

- **Python 3.11 or later**
- **HiGHS solver** — installed automatically with `samba-core` via `highspy`

> CBC is an alternative open-source solver. Install it with
> `conda install -c conda-forge coincbc` and pass `--solver cbc` to `samba run`.

---

## Installation

### From PyPI (recommended)

```bash
pip install samba-core[cli]
```

The `[cli]` extra installs [Typer](https://typer.tiangolo.com/) and
[Rich](https://rich.readthedocs.io/) for the command-line interface. Omit it if you
only need the Python API.

### From source (development)

SAMBA uses [uv](https://docs.astral.sh/uv/) for development environments:

```bash
git clone https://github.com/sambaenergies/samba.git
cd samba
uv sync --all-extras            # creates .venv from uv.lock (dev + cli + service)
uv run pre-commit install       # optional: installs ruff + mypy hooks
```

Verify the installation:

```bash
uv run samba info
```

Expected output:

```
╭─ SAMBA Environment ─────────────────╮
│ SAMBA version          5.3.0         │
│ Python version         3.11.x        │
│ HiGHS (default solver) ✓ available   │
╰──────────────────────────────────────╯
```

---

## Your First Run

SAMBA ships with an annotated example scenario:

```bash
samba run examples/base_scenario.yaml -o results/
```

This will:

1. Load and validate `examples/base_scenario.yaml`
2. Resolve load and weather arrays from the files referenced in the YAML
3. Optimise the system using HiGHS
4. Write a timestamped results directory under `results/`
5. Print a summary table to the terminal

---

## Understanding the Output

After a successful run, a directory like
`results/SAMBA-Demo_20260303_120000/` is created containing:

| File | Contents |
|---|---|
| `kpis.json` | Key performance indicators: NPC, LCOE, RE fraction, LPSP, sizing |
| `sizing.csv` | Optimal capacity of each component |
| `economics.json` | Full economic breakdown: capex, O&M, replacement, grid, salvage |
| `dispatch.parquet` | Hourly dispatch time series (8760 rows, all component flows) |
| `dispatch.csv` | CSV mirror of `dispatch.parquet` |
| `metadata.json` | Run provenance: SAMBA version, solver, timestamp, scenario hash |
| `scenario.yaml` | Frozen copy of the resolved scenario (with all defaults filled in) |
| `tariff.parquet` | Resolved hourly buy/sell price arrays |

**Read `kpis.json` first.** Key fields:

```json
{
  "npc": 82451.23,           // Net Present Cost [$]
  "lcoe": 0.187,             // Levelised Cost of Energy [$/kWh]
  "renewable_fraction": 0.642, // Share of load met by renewables [0-1]
  "lpsp": 0.0,               // Loss of Power Supply Probability [0-1]
  "total_pv_generation": 11240.5 // Annual PV generation [kWh]
}
```

**See `sizing.csv` for optimal sizes:**

```
component,capacity,unit
pv,6.3,kW
battery_energy,12.4,kWh
inverter,4.8,kW
```

---

## Validate Before Running

Check a scenario file for errors without solving:

```bash
samba validate my_scenario.yaml
```

Exits with code `0` on success or prints a detailed error list with field paths on
failure — useful when authoring new scenario files.

---

## Python API Quick Example

```python
from pathlib import Path
import numpy as np
import samba
from samba.scenario import load_scenario
from samba.input_resolver import resolve_arrays

# Load and validate the scenario
scenario = load_scenario("examples/base_scenario.yaml")

# Resolve 8760-hour arrays from the scenario's data sources
base_dir = Path("examples")
load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, base_dir)

# Run the full pipeline
result = samba.run(
    scenario,
    load_kw=load_kw,
    pv_per_kwp=pv_per_kwp,
    output_dir="results/",
)

print(f"NPC:  ${result.kpis['npc']:,.0f}")
print(f"LCOE: ${result.kpis['lcoe']:.3f}/kWh")
print(f"RE:   {result.kpis['renewable_fraction']:.1%}")
```

---

## Next Steps

- **[Scenario Reference](scenario-reference.md)** — Document every YAML field
- **[CLI Reference](cli-reference.md)** — All command options and exit codes
- **[API Reference](api-reference.md)** — Python API for advanced use
- **[Known Limitations](known-limitations.md)** — What v1 does and does not model
