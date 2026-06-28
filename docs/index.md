# SAMBA Documentation

**S**ystems **A**dvisor for **M**icrogrids & **B**uilding **A**nalysis

SAMBA is an open-source Python library for optimal sizing and techno-economic
analysis of hybrid energy systems. It compiles a user-defined scenario (described in a
YAML file) into a linear program, solves it with an open-source solver, and produces
a structured directory of result artifacts.

---

## Documentation Contents

| Document | Description |
|---|---|
| [Getting Started](getting-started.md) | Install SAMBA and run your first scenario |
| [Scenario Reference](scenario-reference.md) | Complete YAML schema reference |
| [CLI Reference](cli-reference.md) | Command-line interface: `samba run`, `validate`, `info`, `serve` |
| [API Reference](api-reference.md) | Python API for use in scripts and notebooks |
| [Known Limitations](known-limitations.md) | What v1 does and does not model |
| [About](about.md) | Project overview and motivation |

Developer / contributor references:

| Document | Description |
|---|---|
| [Developer: Results Contract](developer/results-contract.md) | Output artifact schema |
| [Developer: Architecture](developer/architecture.md) | Package layout and design decisions |
| [Developer: Domain Model](developer/domain-model.md) | Component physics and oemof-solph mapping |

---

## What SAMBA Does

1. **Reads** a scenario YAML that describes your energy system: location, weather,
   load profile, available components (PV, battery, wind, diesel, inverter, grid) and
   their costs, tariff structure, economic parameters and constraints.
2. **Solves** a linear program (via [oemof-solph](https://oemof-solph.readthedocs.io)
   + [HiGHS](https://highs.dev)) to find the cost-minimising component sizes and
   hourly dispatch over a one-year simulation horizon.
3. **Computes** post-processing economics: NPC, LCOE, CRF, replacement cycles,
   salvage value, grid cost projection with escalation, ITC incentives.
4. **Writes** a self-contained results directory with all artifacts:
   `dispatch.parquet`, `kpis.json`, `economics.json`, `sizing.csv`, `metadata.json`.

---

## Quick Example

```bash
pip install samba-core[cli]
samba run examples/base_scenario.yaml -o results/
```

Output:

```
╭─ SAMBA Results ─────────────────────────╮
│ NPC:     $ 82,451    LCOE:  $0.187/kWh  │
│ PV:       6.3 kW     Battery:  12.4 kWh │
│ RE:       64.2 %     LPSP:      0.000 % │
╰─────────────────────────────────────────╯
Results written to: results/my-scenario_20260303_120000/
```

---

## Acknowledgements

SAMBA is an independently-developed project with its own models, data, and
architecture. See [Acknowledgements](acknowledgements.md) for the project that
inspired it and the citation.

---

## License

- [Mozilla Public License 2.0](https://mozilla.org/MPL/2.0/)
