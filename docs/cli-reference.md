# CLI Reference

The SAMBA CLI is installed as the `samba` command when you install
`samba-core[cli]`.

```bash
samba --help
```

---

## `samba run`

Run the full optimisation pipeline on a scenario YAML file.

```
samba run SCENARIO [OPTIONS]
```

### Arguments

| Argument | Description |
|---|---|
| `SCENARIO` | Path to the scenario YAML file. **Required.** |

### Options

| Option | Short | Default | Description |
|---|---|---|---|
| `--output-dir PATH` | `-o` | `results` | Base directory for run artifacts. A timestamped sub-directory is created inside. |
| `--solver NAME` | `-s` | `appsi_highs` | LP solver name. `appsi_highs` (HiGHS, default) or `cbc`. |
| `--time-limit SECS` | | `600` | Maximum solver wall-clock time in seconds. |
| `--verbose` | `-v` | `False` | Print solver output to terminal. |

### Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success — optimal solution found, artifacts written |
| `1` | Validation or file error — scenario YAML invalid or file not found |
| `2` | Solver error — infeasible, no solver found, or time limit exceeded |
| `3` | Data pipeline error — weather/load CSV file missing or malformed |
| `4` | Internal error — unexpected exception |

### Example

```bash
# Run with default output directory
samba run my_scenario.yaml

# Specify output directory
samba run my_scenario.yaml -o outputs/feasibility_study/

# Use CBC solver with longer time limit
samba run my_scenario.yaml --solver cbc --time-limit 1200

# Print solver log for debugging
samba run my_scenario.yaml --verbose
```

### Output

On success, a summary panel is printed:

```
╭─ SAMBA Results ────────────────────────────────╮
│ NPC:        $82,451     LCOE: $0.187/kWh        │
│ PV:          6.3 kW     Battery:     12.4 kWh   │
│ Inverter:    4.8 kW     Wind:         0.0 kW    │
│ RE fraction: 64.2 %     LPSP:         0.000 %   │
│ Diesel:      0.0 L                              │
│                                                 │
│ Results written to: outputs/.../               │
╰─────────────────────────────────────────────────╯
```

---

## `samba validate`

Validate a scenario YAML file without running a solve.

```
samba validate SCENARIO
```

Checks schema compliance, required fields, cross-field constraints, and file path
references (weather CSV, load CSV).

### Arguments

| Argument | Description |
|---|---|
| `SCENARIO` | Path to the scenario YAML file. **Required.** |

### Exit Codes

| Code | Meaning |
|---|---|
| `0` | Scenario is valid |
| `1` | Validation error or file not found |

### Example

```bash
samba validate my_scenario.yaml
# ✓ Scenario is valid: my_scenario.yaml

samba validate bad_scenario.yaml
# ✗ Validation errors:
#   components.pv.derating_factor: value must be between 0 and 1
#   tariff.sell: rate_per_kwh is required when sell.type='flat'
```

---

## `samba info`

Display environment and dependency information.

```
samba info
```

Shows the installed version of SAMBA and its core dependencies, and reports whether
the default solver (HiGHS) is available. Useful for bug reports and environment
debugging.

### Example output

```
╭─ SAMBA Environment ──────────────────────────╮
│ SAMBA version          1.0.0                  │
│ Python version         3.11.9                 │
│ oemof-solph version    0.6.4                  │
│ Pyomo version          6.7.3                  │
│ HiGHS (default solver) ✓ available (highspy)  │
│ CBC solver             ✗ not found            │
│ samba location         /path/to/samba/        │
╰───────────────────────────────────────────────╯
```

---

## `samba pareto`

Generate a Pareto front of the cost vs CO₂-emissions trade-off (one solve per point).

```bash
samba pareto SCENARIO [OPTIONS]
```

### Options

| Option | Default | Description |
|---|---|---|
| `-o`, `--output-dir` | `pareto` | Directory for per-point artifacts + `pareto_front.csv` / `.json` |
| `-n`, `--n-points` | `10` | Number of points on the front |
| `-m`, `--method` | `weighted_sum` | `weighted_sum` (fast, convex hull only) or `epsilon` (captures non-convex regions) |
| `-s`, `--solver` | `appsi_highs` | LP solver |
| `--time-limit` | `600` | Solver time limit per point (s) |

The **epsilon-constraint** method (`--method epsilon`) caps emissions at a series
of thresholds and minimises cost, recovering non-convex frontier regions that the
weighted-sum method silently omits. See [Known Limitations](known-limitations.md).

```bash
samba pareto my_scenario.yaml -n 12 --method epsilon -o results/pareto/
```

---

## `samba fetch-weather`

Fetch a year of NSRDB weather for a site from the NREL API and cache it locally as
an NSRDB-format CSV (so subsequent runs are reproducible and offline).

```bash
samba fetch-weather --lat 37.77 --lon -122.42 --year 2020
```

### Options

| Option | Description |
|---|---|
| `--lat` | Site latitude [deg] (required) |
| `--lon` | Site longitude [deg] (required) |
| `--year` | Calendar year to fetch (required) |
| `--api-key` | NREL API key (or set `NREL_API_KEY`) |
| `--email` | NREL API email (or set `NREL_API_EMAIL`) |
| `-o`, `--cache-dir` | Cache directory (default `~/.cache/samba/weather`) |

Get a free key at <https://developer.nlr.gov/signup/>. You can also skip this
command and set `weather: { source: nsrdb }` in a scenario to auto-fetch + cache.

---

## `samba fetch-cop-data`

Source a heat-pump COP dataset from a public listing (e.g. the NEEP cold-climate
ASHP list) and normalise it into SAMBA's `outdoor_temp_c,cop_heating,cop_cooling`
schema for `heat_pump.cop_source: "dataset"`. The output carries a provenance
header (source, retrieval date, raw checksum, model count).

```bash
# normalise an already-downloaded export
samba fetch-cop-data --from-file neep_export.csv -o cop_dataset.csv

# or download then normalise
samba fetch-cop-data --url "https://…/neep_export.csv" -o cop_dataset.csv
```

### Options

| Option | Description |
|---|---|
| `--from-file` | Normalise an already-downloaded raw export CSV |
| `--url` | Download a raw export from this URL, then normalise |
| `-o`, `--out` | Output curated CSV (default `cop_dataset.csv`) |
| `--source` | Provenance label written into the header |

Provide exactly one of `--from-file` / `--url`. The default column mapping targets
the NEEP export; confirm it against a current download and adjust if the format has
changed. **SAMBA ships no third-party performance data — verify the source's
redistribution license before committing the curated CSV** (the default output path
is git-ignored). A representative, license-clean example ships at
`examples/content/cop_ashp_reference.csv`.

---

## `samba serve`

Run the SAMBA REST service (FastAPI). See [Deployment](deployment.md) for
configuration (env vars), persistence, and Docker.

```bash
samba serve --host 0.0.0.0 --port 8000
```

---

## Shell Completion

SAMBA supports tab completion for bash, zsh, and fish via Typer:

```bash
# bash
samba --install-completion bash

# zsh
samba --install-completion zsh
```
