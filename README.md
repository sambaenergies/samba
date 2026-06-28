<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/samba-logo-white.svg" />
    <img src="docs/assets/samba-logo.svg" alt="SAMBA logo" width="180" />
  </picture>
</p>

# SAMBA

**Systems Advisor for Microgrids & Building Analysis** — optimal sizing and
techno-economic analysis of hybrid energy systems.

[![CI](https://github.com/sambaenergies/samba/actions/workflows/ci.yml/badge.svg)](https://github.com/sambaenergies/samba/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/samba-core)](https://pypi.org/project/samba-core/)
[![License: MPL 2.0](https://img.shields.io/badge/license-MPL--2.0-brightgreen)](https://mozilla.org/MPL/2.0/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)

Describe a system in a YAML file; SAMBA formulates and solves a linear program
(oemof-solph + HiGHS) for the least-cost component sizing and hourly dispatch,
then writes a structured directory of result artifacts.

## Features

- **Provably-optimal sizing** (LP/MILP) — PV, wind, battery, diesel, inverter, grid, EV/V2G
- **Thermal domain** — heat pump, thermal storage, and gas boiler with merit-order dispatch
- **8 tariff structures** — flat, TOU, tiered, seasonal, monthly (and combinations), plus demand charges and NEM/net-billing
- **Multi-objective** cost + CO₂ with epsilon-constraint Pareto fronts
- **Real-world data** — NSRDB weather fetch, bifacial PV, battery degradation, load-profile templates
- **Four ways to use it** — Python API, CLI, REST service, and a Vue 3 + Tauri desktop/web UI
- **Standardised artifacts** — `kpis.json`, `dispatch.parquet`, `economics.json`, `sizing.csv`

## Quick start

```bash
pip install samba-core[cli]
samba run examples/base_scenario.yaml -o results/
```

```python
import samba
from samba.scenario import load_scenario
from samba.input_resolver import resolve_arrays
from pathlib import Path

scenario = load_scenario("examples/base_scenario.yaml")
load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, Path("examples"))
result = samba.run(scenario, load_kw=load_kw, pv_per_kwp=pv_per_kwp, output_dir="results/")
print(f"NPC ${result.kpis['npc']:,.0f}  ·  LCOE ${result.kpis['lcoe']:.3f}/kWh")
```

The default solver is **HiGHS** (installed via `highspy`); CBC also works
(`--solver cbc`).

## Desktop & Web UI

A [Vue 3 + Tauri front-end](ui/) talks to the `samba serve` REST API and runs in
the browser or as a native desktop app:

```bash
samba serve --data-dir examples       # REST API on http://127.0.0.1:8000
cd ui && npm install && npm run dev    # UI on http://localhost:1420
```

## Documentation

| Document | Description |
|---|---|
| [Getting Started](docs/getting-started.md) | Install and run your first scenario |
| [Scenario Reference](docs/scenario-reference.md) | Complete YAML schema reference |
| [Thermal Components](docs/thermal-components.md) | Heat pump, thermal storage, gas supply |
| [CLI Reference](docs/cli-reference.md) | `run`, `validate`, `info`, `serve`, … |
| [API Reference](docs/api-reference.md) | Python API |
| [Deployment](docs/deployment.md) | REST service (Docker, persistence, CI) |
| [Desktop / Web UI](ui/README.md) | Running and developing the front-end |
| [Known Limitations](docs/known-limitations.md) | What SAMBA does and does not model |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Development uses [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/sambaenergies/samba.git
cd samba && uv sync --all-extras
```

## License

[Mozilla Public License 2.0](LICENSE). See [Acknowledgements](docs/acknowledgements.md).
