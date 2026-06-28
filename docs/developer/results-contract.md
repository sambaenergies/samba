# Developer: Results Contract

This document defines the exact output artifacts produced by a SAMBA run. All
consumers — CLI, Python API callers, UI, benchmarks, and post-processing scripts —
depend on this contract.

> **Canonical version:** This file is the authoritative results contract.

---

## Run Directory Structure

Every run produces a self-contained directory:

```
<output_dir>/
  <run_id>/
    scenario.yaml          # Frozen copy of resolved input (all defaults filled in)
    metadata.json          # Provenance and run information
    kpis.json              # Key performance indicators
    sizing.csv             # Optimal component sizes
    dispatch.parquet       # Hourly dispatch time series (8760 rows, Snappy compressed)
    dispatch.csv           # CSV mirror of dispatch.parquet
    economics.json         # Detailed economic breakdown
    tariff.parquet         # Resolved hourly buy/sell price arrays (8760 rows)
```

`<run_id>` is derived from `{scenario.project.name}_{YYYYMMDD_HHMMSS}` with unsafe
characters replaced by underscores.

---

## `metadata.json`

```json
{
  "run_id": "my-scenario_20260303_120000",
  "samba_version": "1.0.0",
  "timestamp_utc": "2026-03-03T12:00:00Z",
  "wall_time_seconds": 12.4,
  "solver": {
    "name": "appsi_highs",
    "time_limit_s": 600
  },
  "scenario_hash": "sha256:abcdef1234567890",
  "status": "optimal"
}
```

---

## `kpis.json`

```json
{
  "npc": 82451.23,
  "lcoe": 0.187,
  "renewable_fraction": 0.642,
  "lpsp": 0.0,
  "total_pv_generation": 11240.5,
  "dg_fuel_consumption_liters": 0.0,
  "grid_annual_bought_kwh": 3210.4,
  "grid_annual_sold_kwh": 1540.2
}
```

All monetary values are in the scenario's `project.currency`.

---

## `sizing.csv`

```csv
component,capacity,unit
pv,6.3,kW
battery_energy,12.4,kWh
inverter,4.8,kW
wind_turbine,0.0,kW
diesel_generator,0.0,kW
```

Components with capacity `0.0` were either disabled in the scenario or sized to zero
by the optimiser.

---

## `dispatch.parquet` / `dispatch.csv`

8760 rows (one per hour of the simulation year). Columns:

| Column | Unit | Description |
|---|---|---|
| `pv_dc` | kW | PV DC generation |
| `battery_charge` | kW | Battery charge power |
| `battery_discharge` | kW | Battery discharge power |
| `battery_soc` | kWh | Battery state of charge |
| `inverter_ac` | kW | Inverter AC output |
| `grid_buy` | kW | Power purchased from grid |
| `grid_sell` | kW | Power exported to grid |
| `dg_ac` | kW | Diesel generator output |
| `wt_ac` | kW | Wind turbine output |
| `load` | kW | Electrical demand |
| `unmet_load` | kW | Unmet demand (should be ≈ 0 for LPSP ≈ 0) |

Columns for absent components are omitted.

---

## `economics.json`

Top-level structure:

```json
{
  "total_investment": 18240.0,
  "capex": { "pv": 14918.4, "battery": 0.0, "inverter": 1508.0, ... },
  "total_replacement_npv": 2150.3,
  "total_om_npv": 5430.1,
  "om_annual": { "pv": 191.3, "battery": 0.0, ... },
  "fuel_annual_cost": 0.0,
  "fuel_total_npv": 0.0,
  "total_salvage_npv": 1230.5,
  "grid": {
    "annual_bought_cost_yr1": 741.2,
    "annual_sold_revenue_yr1": 64.7,
    "annual_service_charge": 180.0,
    "total_bought_npv": 12340.5,
    "total_sold_npv": 1078.2,
    "total_net_npv": 11442.3
  },
  "npc": 82451.23,
  "lcoe": 0.187,
  "crf": 0.0707,
  "cashflow_table": [ ... ]
}
```

---

## `tariff.parquet`

8760 rows. Columns: `cbuy` ($/kWh), `csell` ($/kWh).

---

## Schema Version Policy

The results contract follows the scenario schema version. Breaking changes (new
required fields, renamed fields, changed units) require a schema version bump. The
`metadata.json` `samba_version` field allows consumers to detect version mismatches.
