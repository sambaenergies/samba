# Thermal Components Guide

SAMBA v3 adds a thermal domain alongside the existing electrical domain.
Thermal components model building heating and cooling, heat-pump dispatch,
thermal buffer storage, and natural gas supply — all linked by LP dispatch
to the electrical bus and economic objective.

---

## Bus Topology

```
                  ┌─────────────────────────────┐
                  │       Electrical Bus         │
                  │  (PV, Battery, Grid, etc.)   │
                  └──────────────┬───────────────┘
                                 │  HP electricity draw
                  ┌──────────────▼───────────────┐
                  │        Heat Pump             │
                  │  (air→water; catalog sizing) │
                  └───────┬──────────┬───────────┘
                          │          │
             heating kW_th│          │cooling kW_th
                  ┌───────▼──┐    ┌──▼────────┐
                  │ Heating  │    │ Cooling   │
                  │   Bus    │    │   Bus     │
                  └──┬───────┘    └───────────┘
                     │
          ┌──────────┼──────────────────┐
          │          │                  │
  ┌───────▼──┐  ┌────▼──────┐    ┌─────▼──────┐
  │ Thermal  │  │   Gas     │    │  Heating   │
  │ Storage  │  │  Boiler   │    │   Load     │
  │  (tank)  │  │ (fallback)│    │ (CSV/DD)   │
  └──────────┘  └───────────┘    └────────────┘
```

Each bus component has an oemof `Bus` node; heat pump and gas boiler are
`Transformer` components; thermal storage is a `GenericStorage` component.

---

## Heat Pump

### Overview

The heat pump component models an air-source heat pump that provides heating
and / or cooling to the building. It draws electricity from the electrical
bus and produces thermal output on the heating and / or cooling bus.

```yaml
components:
  heat_pump:
    mode: "both"                  # "heating_only" | "cooling_only" | "both"
    capacity_kw_th: null          # float > 0 or null for investment sizing
    catalog_model: "auto"         # "auto" or a specific model ID (e.g. "0301B")
    capex_per_kw_th: 600.0        # $/kW_th installed
    opex_fraction: 0.01           # annual O&M as fraction of capex
    lifetime_years: 15            # component economic lifetime
```

### Catalog Sizing

When `catalog_model: "auto"`, SAMBA selects the smallest standard nominal model
(1.5–5 ton / 18 000–60 000 BTU/hr) whose rated capacity covers the peak hourly
thermal demand in the scenario. The COP itself is independent of the unit size
(it is an intensive thermodynamic property); the size only sets the rated output.

### COP Model

The COP is supplied as a time-varying conversion factor on the heat-pump
converter (`thermal_output[t] = COP[t] × elec_input[t]`). The `heat_pump.cop_source`
field selects how it is produced:

| `cop_source` | What it does | Data needed |
|---|---|---|
| `catalog` *(default)* | Physics-based Carnot-fraction COP, computed hourly from the outdoor temperature. License-clean, transparent, reproducible — nothing to supply. | none |
| `fixed` | Constant COP via `fixed_cop_heating` / `fixed_cop_cooling`. | none |
| `dataset` | Fit COP(T) curves from a curated CSV of rating points (`cop_dataset_path`). | a local CSV |

> **Note on naming.** `catalog` selects the *physics* model — it does not load any
> manufacturer catalog. The default deliberately uses first principles, not vendor
> performance tables, so SAMBA ships no third-party data.

#### Default: physics (Carnot-fraction)

Derived from first principles as a fraction of the reversible (Carnot) limit,
evaluated hourly against the outdoor dry-bulb temperature. See
`samba/thermal/cop.py` and `samba/thermal/constants.py`.

**Heating** (cold side = outdoor air, hot side = condenser supply temperature):

$$
\text{COP}_h = f_h \cdot \frac{T_\text{supply}}{T_\text{supply} - T_\text{db,out}}
$$

**Cooling** (cold side = indoor wet-bulb, hot side = outdoor air):

$$
\text{COP}_c = f_c \cdot \frac{T_\text{wb,in}}{T_\text{db,out} - T_\text{wb,in}}
$$

(all temperatures absolute). $T_\text{db,out}$ is the outdoor dry-bulb temperature
[°C] read from the weather file; $T_\text{wb,in}$ is the indoor wet-bulb
temperature from the Stull (2011) approximation; and $f_h$, $f_c$ are practical
second-law efficiencies (fractions of the Carnot COP achieved by real equipment,
per ASHRAE *Fundamentals*).

Each COP value is clipped to the range $[1.0, 8.0]$ to enforce energy
conservation and cap the Carnot singularity at near-zero temperature lift.

#### Opt-in: dataset-fitted COP

For empirical performance, set `cop_source: "dataset"` and point
`cop_dataset_path` at a CSV of rating points
(`outdoor_temp_c, cop_heating, cop_cooling`). SAMBA fits a low-order polynomial
COP(T) curve per mode (`samba/thermal/cop_dataset.py`) and evaluates it hourly,
clipped to the same $[1.0, 8.0]$ bounds. At least two points per fitted mode are
required. A relative `cop_dataset_path` resolves against the scenario file's
directory.

```yaml
heat_pump:
  cop_source: "dataset"
  cop_dataset_path: "content/cop_ashp_reference.csv"
```

SAMBA ships one curated dataset: `examples/content/cop_ashp_reference.csv` — a
**license-clean representative** curve (typical published AHRI rating-point
values, *not* a specific manufacturer's data). The runnable example
`examples/grid_pv_heat_pump_dataset.yaml` uses it. This file is a demonstration /
reference fixture; it is **not** the shipped default COP model.

##### Using real product data (NEEP) — local only

To fit against a real cold-climate ASHP population, fetch a dataset locally with
the `samba fetch-cop-data` helper (e.g. the NEEP cold-climate ASHP list), which
normalises a wide per-model export to the curated schema and writes a provenance
header:

```bash
samba fetch-cop-data --from-file neep_export.csv -o cop_dataset.csv
```

> **Local use only.** Third-party performance data (NEEP included) is generally
> **not** redistribution-permissive. Fetched output is written to a git-ignored
> path by default — **do not commit or share it** unless you have confirmed the
> source grants those rights. The fetch tool records the source and checksum so
> the decision is auditable. Confirm the export's column names against
> `NEEP_RATING_POINTS` in `samba/thermal/cop_fetch.py`, as NEEP's format changes
> over time.

### KPIs

| KPI | Description |
|---|---|
| `mean_cop_heating` | Annual-mean heating COP (energy-weighted) |
| `mean_cop_cooling` | Annual-mean cooling COP (energy-weighted) |
| `annual_heat_produced_kwh` | Total heating energy delivered [kWh_th] |
| `annual_cool_produced_kwh` | Total cooling energy delivered [kWh_th] |
| `annual_hp_elec_kwh` | Total HP electricity consumed [kWh_e] |
| `thermal_lpsp_heating` | Fraction of heating hours with unmet demand |
| `thermal_lpsp_cooling` | Fraction of cooling hours with unmet demand |

---

## Thermal Load

Building heating and cooling demand can be specified as:

### Option 1: Hourly CSV

```yaml
load:
  thermal:
    source: "csv"
    heating_csv: "heating_demand.csv"   # 1-column CSV, header + 8760 rows [kW_th]
    cooling_csv: "cooling_demand.csv"   # optional; omit for heating-only
```

CSV files must have exactly one header row (column name) followed by 8760 data
rows (one per hour). Relative paths are resolved relative to the scenario YAML
file location.

### Option 2: Degree-Day Model

```yaml
load:
  thermal:
    source: "degree_day"
    ua_kw_per_degC: 0.5          # building UA value [kW/°C]
    heating_setpoint_c: 20.0     # indoor heating setpoint [°C]
    cooling_setpoint_c: 26.0     # indoor cooling setpoint [°C]
```

The degree-day model calculates hourly heating/cooling demand from outdoor
temperature in the weather file:

$$
Q_h(t) = \text{UA} \times \max(T_\text{heat set} - T_\text{out}(t),\ 0)
$$

$$
Q_c(t) = \text{UA} \times \max(T_\text{out}(t) - T_\text{cool set},\ 0)
$$

**Limitations:** The degree-day model does not account for:

- Solar heat gains through windows
- Internal heat gains (occupants, appliances)
- Latent (humidity) loads
- Thermal lag / building thermal mass
- Multi-zone building geometries

For detailed building analysis, pre-compute an 8760-h load profile with
EnergyPlus or OpenStudio and supply it as a CSV.

---

## Thermal Storage

A hot-water buffer tank that stores thermal energy against dispatch.

```yaml
components:
  thermal_storage:
    capacity_kwh_th: null        # float > 0 or null for investment sizing
    capex_per_kwh_th: 20.0       # $/kWh_th installed capacity
    charge_efficiency: 0.98      # charging round-trip efficiency
    discharge_efficiency: 0.98   # discharging round-trip efficiency
    loss_rate_per_hour: 0.002    # fractional standby loss per hour (0.2% default)
    lifetime_years: 20
```

### Investment Sizing

When `capacity_kwh_th: null`, the LP optimises tank size to minimise NPC,
trading off capex against reduced HP operating cost (e.g. by shifting HP
operation to off-peak TOU periods).

### Loss Rate Guidance

| Tank insulation | Typical loss rate |
|---|---|
| Well-insulated buffer (100 L, 80 mm foam) | 0.001–0.003 / h |
| Lightly insulated (50 mm fibreglass) | 0.004–0.008 / h |
| Uninsulated steel tank | 0.010–0.020 / h |

### KPIs

| KPI | Description |
|---|---|
| `thermal_storage_capex` | Capital cost of installed tank [$] |
| `annual_thermal_storage_cycles` | Equivalent full charge-discharge cycles per year |

---

## Gas Supply

Natural gas boiler / furnace as heating backup or primary supply.

```yaml
components:
  gas_supply:
    boiler_efficiency: 0.85      # LHV thermal efficiency [0–1]
    capex: 2000.0                # $/unit installed cost
    opex_per_year: 50.0          # $/yr fixed O&M
    lifetime_years: 20
    co2_per_kwh_th_gas: 0.205    # kg CO2 per kWh_th gas consumed (LHV basis)
    rate:
      type: "flat"               # "flat" | "seasonal" | "tiered"
      rate_per_kwh_th: 0.04      # $/kWh_th gas for flat rate
```

### Unit Conversions

Gas is priced and billed in thermal units (kWh_th LHV basis) internally.
Common conversions:

| Unit | kWh_th |
|---|---|
| 1 therm (US) | 29.31 kWh_th |
| 1 GJ | 277.78 kWh_th |
| 1 MBtu | 293.07 kWh_th |
| 1 m³ natural gas (approx) | ~10.55 kWh_th HHV |

> **LHV vs HHV:** SAMBA uses LHV throughout. To convert HHV rates to LHV, divide
> by the HHV/LHV ratio (~1.11 for natural gas). For condensing boilers with
> recovery efficiency > 1.0 on LHV basis, cap `boiler_efficiency: 1.0` to avoid
> non-physical inputs.

### Gas Rate Structures

```yaml
# Flat rate
rate:
  type: "flat"
  rate_per_kwh_th: 0.04

# Seasonal rate (winter/summer)
rate:
  type: "seasonal"
  summer_rate_per_kwh_th: 0.035
  winter_rate_per_kwh_th: 0.050
  summer_months: [5, 6, 7, 8, 9, 10]

# Tiered rate (monthly blocks)
rate:
  type: "tiered"
  tiers:
    - limit_kwh_th: 500
      rate_per_kwh_th: 0.03
    - limit_kwh_th: null
      rate_per_kwh_th: 0.045
```

### HP vs Gas Merit Order

When both `heat_pump` and `gas_supply` are present, the LP performs automatic
merit-order dispatch: for each hour, it selects the heating source that
minimises total cost.

Approximate breakeven (ignoring capex):

$$
\frac{P_\text{elec}}{\text{COP}_h} \approx \frac{P_\text{gas}}{\eta_\text{boiler}}
\implies P_\text{elec} \approx P_\text{gas} \times \frac{\text{COP}_h}{\eta_\text{boiler}}
$$

Example: gas $0.04/kWh_th, boiler η=0.85, COP_h=4.5
→ HP breakeven electricity price = $0.04 × 4.5 / 0.85 ≈ **$0.21/kWh_e**

Above $0.21/kWh_e electricity, gas is cheaper. Below, HP is cheaper.

### KPIs

| KPI | Description |
|---|---|
| `annual_gas_consumption_kwh_th` | Gas consumed (LHV thermal) [kWh_th] |
| `annual_gas_cost_usd` | Annual gas bill [$] |
| `annual_gas_co2_kg` | Annual gas CO₂ emissions [kg] |
| `gas_boiler_npc` | Net present cost of gas supply component [$] |
| `gas_boiler_capex` | Capital cost of boiler installation [$] |

---

## Thermal LPSP

Loss of Thermal Load Probability (LPSP) is defined per mode:

$$
\text{LPSP}_\text{heat} = \frac{\sum_t \max(Q_h^\text{demand}(t) - Q_h^\text{supply}(t),\ 0)}{\sum_t Q_h^\text{demand}(t)}
$$

and analogously for cooling.

Set `constraints.thermal_lpsp_max` to enforce a hard reliability limit:

```yaml
constraints:
  thermal_lpsp_max: 0.0    # 0.0 = no unmet load allowed (fully met)
```

---

## Example: Grid + HP Thermal Scenario

```yaml
schema_version: "2.0"

project:
  name: "HP Heating Example"
  year: 2025
  lifetime_years: 20
  discount_rate_nominal: 0.06
  inflation_rate: 0.02

location:
  latitude: 37.77
  longitude: -122.42
  timezone: "America/Los_Angeles"

weather:
  source: "csv"
  csv_path: "weather.csv"          # NSRDB-format CSV; required for HP COP curves

load:
  source: "generic_annual_total"
  annual_kwh: 6000.0
  thermal:
    enabled: true
    source: "degree_day"
    building_ua_kw_per_k: 0.5
    heating_setpoint_c: 20.0
    cooling_setpoint_c: 26.0

components:
  inverter:
    capacity_kw: null              # LP sizes inverter
    capex_per_kw: 314.0
    efficiency: 0.96

  grid:
    enabled: true
    capacity_kw: 20.0

  heat_pump:
    enabled: true
    mode: "both"
    sizing: "catalog_auto"         # smallest catalog model that meets peak demand
    cop_source: "catalog"          # physics-based Carnot-fraction COP
    capex: 4000.0
    lifetime_years: 15

  thermal_storage:
    enabled: true
    sizing: "investment"           # LP sizes the tank
    capacity_max_kwh_th: 100.0
    capex_per_kwh_th: 15.0
    lifetime_years: 20

tariff:
  buy:
    type: "flat"
    rate_per_kwh: 0.12

constraints:
  thermal_lpsp_max: 0.0

objective:
  type: "cost"
```

---

## See Also

- [Scenario Reference](scenario-reference.md) — full YAML schema for v3 thermal keys
- [Known Limitations](known-limitations.md) — thermal modelling scope
- [Golden Scenarios g13–g19](../tests/goldens/) — regression benchmarks for all thermal components
