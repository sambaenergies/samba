# Scenario Reference

A SAMBA scenario is a YAML file that completely describes an energy system
optimisation problem. SAMBA validates, solves, and post-processes the scenario to
produce result artifacts.

See [`examples/base_scenario.yaml`](../examples/base_scenario.yaml) for a fully
annotated example.

---

## Top-Level Structure

```yaml
schema_version: "1.0"   # required

project:    { ... }
location:   { ... }
weather:    { ... }
load:       { ... }
components: { ... }
tariff:     { ... }
constraints: { ... }
objective:  { ... }
```

---

## `schema_version`

Must be one of `"1.0"`, `"1.1"`, `"2.0"`, `"3.0"`, or `"4.0"`. SAMBA rejects files with an unknown or missing version.

| Version | Features |
|---|---|
| `"1.0"` | v1 core: PV, Battery, Wind, DG, Grid, Inverter |
| `"1.1"` | Backwards-compatible alias for `"1.0"` |
| `"2.0"` | v2: multi-objective, DG economics, EV, KiBaM, endogenous tiering |
| `"3.0"` | v3: heat pump, thermal storage, gas supply, thermal loads |
| `"4.0"` | v4: demand charges, NEM, epsilon-constraint Pareto, battery degradation, bifacial PV, NSRDB fetch, load templates |

---

## `project`

Economic and simulation parameters.

```yaml
project:
  name: "My Microgrid"          # string; used for run directory naming
  year: 2025                    # int; calendar year for tariff day-of-week assignment
  lifetime_years: 25            # int in [1, 40]; economic horizon
  discount_rate_nominal: 0.045  # float in [0, 1]; nominal annual discount rate
  inflation_rate: 0.02          # float in [0, 1]; annual inflation rate
  re_incentive_rate: 0.0        # float in [0, 1); ITC applied to PV + battery capex
  grid_escalation_rate: 0.0     # float in [0, 1]; annual grid price escalation (0 = none)
  budget: null                  # float > 0 or null; hard capital budget limit [$]
  currency: "USD"               # string; display label only
  capex_year: 0                 # int >= 0; year index when initial investment occurs
```

| Field | Default | Notes |
|---|---|---|
| `name` | — | Required. |
| `year` | — | Required. Affects TOU day-of-week resolution. |
| `lifetime_years` | 25 | — |
| `discount_rate_nominal` | 0.045 | Nominal (not real). Real rate ≈ nominal − inflation. |
| `inflation_rate` | 0.02 | — |
| `re_incentive_rate` | 0.0 | Applied to PV + battery capex at year 0. |
| `grid_escalation_rate` | 0.0 | A typical value is 2%/yr (`0.02`). |
| `budget` | null | Null = unconstrained. |
| `currency` | `"USD"` | Display only. |
| `capex_year` | 0 | — |

---

## `location`

Geographic coordinates and timezone. Used by the weather processor to determine
solar geometry.

```yaml
location:
  latitude: 37.77          # float in [-90, 90]
  longitude: -122.42       # float in [-180, 180]; negative = west
  altitude_m: 0.0          # float; metres above sea level
  timezone: "America/Los_Angeles"   # IANA timezone string
```

---

## `weather`

Weather data source for irradiance and temperature.

```yaml
weather:
  source: "csv"
  csv_path: "data/weather.csv"   # path relative to the scenario YAML
```

`csv_path` must point to an **NSRDB-format file**: 3 header rows followed by 8760
data rows with at least the columns `GHI`, `DHI`, `DNI`, `Temperature`, `Wind Speed`.

`source: "nsrdb"` fetches from the NREL API and caches locally — see the v4
additions below.

---

## `load`

Electrical load specification.

### `source: "hourly_csv"`

```yaml
load:
  source: "hourly_csv"
  csv_path: "data/load.csv"   # 8760 rows, single numeric column, kW
  scale_factor: 1.0            # optional multiplier applied after loading
```

### `source: "daily_profile"`

```yaml
load:
  source: "daily_profile"
  daily_profile: [0.3, 0.3, 0.3, 0.3, 0.3, 0.4, 0.6, 1.0, 1.0, 0.9,
                  0.8, 0.8, 0.7, 0.7, 0.7, 0.8, 1.0, 1.0, 0.9, 0.8,
                  0.7, 0.6, 0.5, 0.4]   # 24 values, relative shape
  scale_factor: 2.5   # kW at peak; scales the normalised profile
```

### `source: "monthly_peak"`

```yaml
load:
  source: "monthly_peak"
  monthly_peak: [2.0, 2.1, 2.3, 2.5, 2.8, 3.2,
                 3.4, 3.2, 2.8, 2.5, 2.2, 2.0]   # 12 monthly peak values [kW]
```

### `source: "generic_annual_total"`

Generates a generic load shape (summer peak) and scales it to a specified annual
total.

```yaml
load:
  source: "generic_annual_total"
  annual_kwh: 9500.0    # target annual energy [kWh]; required for this source
  peak_month: "July"    # "January" (winter peak) or "July" (summer peak)
```

### `source: "generic_annual"`

Normalised generic shape; `scale_factor` controls absolute output.

```yaml
load:
  source: "generic_annual"
  peak_month: "July"
  scale_factor: 1.2    # multiplier on the normalised profile
```

---

## `components`

All sub-sections are optional. Omit a component to exclude it from the scenario.

### `pv`

```yaml
components:
  pv:
    enabled: true
    capacity_kw: null        # null = design variable; float = fixed size [kW]
    capex_per_kw: 2368.0     # $/kW installed
    opex_per_kw_yr: 30.36    # $/kW/yr
    lifetime_years: 25
    derating_factor: 0.90    # combined soiling / shading / mismatch [0-1]
    tilt_deg: 33.0           # array tilt from horizontal [degrees]
    azimuth_deg: 180.0       # azimuth (180 = south-facing)
    module_type: "monofacial"
    noct_celsius: 45.0       # Nominal Operating Cell Temperature [°C]
    temp_coeff_pmax: -0.003  # power temperature coefficient [/°C]; negative
```

### `battery`

```yaml
components:
  battery:
    enabled: true
    capacity_kwh: null         # null = design variable; float = fixed size [kWh]
    chemistry: "li_ion"        # only option in v1
    capex_per_kwh: 1450.0
    opex_per_kwh_yr: 10.0
    lifetime_years: 10
    soc_min: 0.10              # minimum state of charge [0-1]
    soc_max: 1.00
    soc_initial: 0.50
    charge_efficiency: 0.9487  # one-way; sqrt(roundtrip) for symmetric
    discharge_efficiency: 0.9487
    c_rate_charge: 1.0         # max charge rate as fraction of capacity [1/hr]
    c_rate_discharge: 1.0
```

### `inverter`

```yaml
components:
  inverter:
    capacity_kw: null       # null = design variable; float = fixed [kW]
    capex_per_kw: 314.0
    opex_per_kw_yr: 0.0
    lifetime_years: 25
    efficiency: 0.96        # DC-to-AC conversion efficiency [0-1]
```

### `wind_turbine`

```yaml
components:
  wind_turbine:
    enabled: true
    count: 1                   # number of identical units (integer)
    rated_power_kw: 1.0        # rated power per turbine [kW]
    hub_height_m: 17.0
    anemometer_height_m: 43.6  # height at which wind speed is measured
    friction_coefficient: 0.14 # Hellman exponent for wind shear
    cut_in_speed_ms: 2.5       # [m/s]
    cut_out_speed_ms: 25.0
    rated_speed_ms: 9.5
    capex_per_unit: 1200.0     # $ per turbine
    opex_per_unit_yr: 48.0
    lifetime_years: 20
```

### `diesel_generator`

```yaml
components:
  diesel_generator:
    enabled: true
    capacity_kw: 5.5           # fixed capacity [kW]; investment not supported in v1
    fuel_curve_slope: 0.4388   # L/hr per kW output
    fuel_curve_intercept: 0.1097  # L/hr per kW rated (no-load consumption fraction)
    fuel_cost_per_l: 1.281     # $/L
    capex_per_kw: 818.0
    opex_per_kw_yr: 0.0        # $/kW/yr (variable O&M use fuel curve)
    lifetime_years: 15
    emissions_kg_co2_per_l: 2.29
```

### `grid`

```yaml
components:
  grid:
    enabled: true
    max_buy_kw: 50.0           # max import power [kW]; null = unconstrained
    max_sell_kw: 50.0          # max export power [kW]; null = unconstrained
    opex_per_kw_yr: 0.0        # annual grid connection fixed cost [$/kW]
    allow_export: true         # must be true to allow grid_sell > 0
```

---

## `tariff`

### `buy` — Buy Rate

Supported types: `flat`, `seasonal`, `monthly`, `tiered`, `seasonal_tiered`,
`monthly_tiered`, `tou`, `ultra_low_tou`.

#### Flat

```yaml
tariff:
  buy:
    type: "flat"
    rate_per_kwh: 0.20
```

#### TOU (Time-of-Use)

```yaml
tariff:
  buy:
    type: "tou"
    tou_schedule:
      - name: "summer_on_peak"
        months: [6, 7, 8, 9]
        weekday: true
        weekend: true
        hours: [16, 17, 18, 19, 20]
        rate_per_kwh: 0.61
      - name: "summer_off_peak"
        months: [6, 7, 8, 9]
        weekday: true
        weekend: true
        hours: [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,21,22,23]
        rate_per_kwh: 0.40
      # ... additional periods covering all 8760 hours
```

Each `TouPeriod` must cover `months` × (`weekday`/`weekend`) × `hours`.
Together all periods must cover all 8760 hours of the year.

#### Tiered

```yaml
tariff:
  buy:
    type: "tiered"
    tiers:
      - limit_kwh: 300
        rate_per_kwh: 0.1018
      - limit_kwh: null    # no limit = top tier
        rate_per_kwh: 0.1175
```

#### Monthly rates

```yaml
tariff:
  buy:
    type: "monthly"
    monthly_rates: [0.54, 0.53, 0.51, 0.49, 0.46, 0.44,
                    0.43, 0.44, 0.46, 0.49, 0.51, 0.54]   # 12 values
```

### `sell` — Sell / Export Rate

#### Flat

```yaml
tariff:
  sell:
    type: "flat"
    rate_per_kwh: 0.042
```

#### Monthly (12 values)

```yaml
tariff:
  sell:
    type: "monthly"
    monthly_rates: [0.058, 0.048, 0.046, 0.043, 0.040, 0.040,
                    0.040, 0.040, 0.038, 0.037, 0.036, 0.035]
```

#### TOU

```yaml
tariff:
  sell:
    type: "tou"
    tou_schedule:
      - name: "on_peak_sell"
        months: [1,2,3,4,5,6,7,8,9,10,11,12]
        weekday: true
        weekend: true
        hours: [16,17,18,19,20]
        rate_per_kwh: 0.08
      # ...
```

### `service_charge`

```yaml
tariff:
  service_charge:
    type: "flat"
    monthly_flat: 15.0    # $/month
```

Tiered service charge:

```yaml
tariff:
  service_charge:
    type: "tiered"
    tiers:
      - limit_kwh: 800
        monthly_charge: 34.29
      - limit_kwh: 1500
        monthly_charge: 46.54
      - limit_kwh: null
        monthly_charge: 66.29
```

---

## `constraints`

```yaml
constraints:
  max_lpsp: 0.0001              # Loss of Power Supply Probability; fraction [0-1]
  min_renewable_fraction: 0.50  # Minimum RE fraction; fraction [0-1]
  max_annual_diesel_l: null     # Max annual diesel [L]; null = unconstrained
  max_battery_cycles_yr: null   # Max battery cycles/yr; null = unconstrained
  force_grid_disconnect: false  # true = treat grid as absent even if grid component present
```

All constraints are hard LP constraints enforced during optimisation.

---

## `objective`

```yaml
objective:
  type: "cost"                # "cost" (default) or "cost_and_emissions"
  emissions_weight: 0.0       # $/kg CO₂ — ignored when type="cost"
```

When `type: cost_and_emissions` the LP minimises:

```
NPC  +  emissions_weight × total_emissions_kg
```

where `total_emissions_kg` is computed from `diesel_generator.co2_per_liter_kg` (default 2.29 kg/L).

> **Pareto front caveat.** The `samba pareto` command sweeps `emissions_weight`
> to trace a cost-vs-emissions front. This is the **weighted-sum** method: it
> recovers only points on the *convex hull* of the true Pareto frontier and
> silently omits non-convex (concave) regions. Treat the output as an
> approximation. See [Known Limitations](known-limitations.md#current-release-caveats-v30x).

---

## v2 Schema Additions

### `battery.chemistry`

```yaml
battery:
  chemistry: "lithium_ion"   # default — standard LP single-tank model
  # OR
  chemistry: "kibam"         # Kinetic Battery Model (lead-acid)
  c_rate_charge: 0.20        # available-charge fraction [0-1]; kibam only
  soc_min: 0.40              # minimum state of charge (depth-of-discharge); kibam only
```

The `kibam` chemistry partitions stored energy into an *available* tank (Q1) and a
*bound* tank (Q2). Charge/discharge rates are limited by `c_rate_charge`. The LP
relaxation may produce O(10) timestep Q1 violations near low SOC — a post-validation
warning is emitted, but LPSP remains 0.

### `diesel_generator` — v2 economics fields

```yaml
diesel_generator:
  capacity_kw: 10.0
  min_load_fraction: 0.0     # LP; set > 0 for minimum stable generation
  co2_per_liter_kg: 2.29     # for multi-objective emissions accounting
  startup_cost: 0.0          # $ per startup event (MILP; set 0 for LP)
  min_up_hours: 0            # minimum on-period [h] (MILP; set 0 for LP)
  min_down_hours: 0          # minimum off-period [h] (MILP; set 0 for LP)
```

> **LP vs MILP**: `startup_cost > 0` or `min_up_hours > 0` activates NonConvex flow
> (MILP). Annual-resolution (8760 h) MILP runs are slow; use 168-h subsets for MILP
> validation. Full-year runs keep `startup_cost: 0.0` and `min_up_hours: 0`.

### `electric_vehicle`

```yaml
components:
  electric_vehicle:
    capacity_kwh: 60.0         # battery capacity
    max_charge_kw: 7.4         # maximum charge rate
    arrival_hour: 18           # hour of arrival (0–23)
    departure_hour: 8          # hour at which EV departs with full SOC
    workdays_per_week: 5       # days/week EV is away (Mon–Fri by default)
    initial_soc: 0.20          # SOC on arrival [0-1]
    target_soc: 1.00           # required SOC at departure [0-1]
    v2g_enabled: false         # true = allow discharge back to grid
    max_discharge_kw: 7.4      # V2G export rate; ignored if v2g_enabled=false
```

EV KPIs added to `kpis.json`:

- `annual_ev_charge_kwh` — total energy delivered to EV
- `annual_ev_discharge_kwh` — total V2G energy exported (0 if V2G disabled)
- `ev_v2g_revenue` — total V2G sell revenue in scenario currency

### `tariff.buy.endogenous_tiering`

```yaml
tariff:
  buy:
    type: "tiered"
    endogenous_tiering: true    # enforce tier limits inside LP (v2)
    tiers:
      - limit_kwh: 500
        rate_per_kwh: 0.10
      - limit_kwh: 1000
        rate_per_kwh: 0.17
      - limit_kwh: null         # no limit = top tier
        rate_per_kwh: 0.24
```

When `endogenous_tiering: true` the LP adds auxiliary variables and constraints to
correctly penalise each consumed kWh in its marginal tier. Without this flag, tiered
rates are applied post-hoc to the dispatch, which over/underestimates costs when the
battery shifts consumption across tier boundaries.

---

## v3 Schema Additions

### `load.thermal` — building thermal loads

Specifies hourly heating and cooling demand. Requires a `weather` file for the
degree-day model (and always for heat-pump COP curves).

```yaml
load:
  thermal:
    source: "degree_day"            # "csv" | "degree_day"

    # --- degree_day source ---
    ua_kw_per_degC: 0.5             # building UA value [kW/°C]; required for degree_day
    heating_setpoint_c: 20.0        # indoor heating setpoint [°C]
    cooling_setpoint_c: 26.0        # indoor cooling setpoint [°C]

    # --- csv source ---
    heating_csv: "heating.csv"      # path to 1-column CSV (header + 8760 rows) [kW_th]
    cooling_csv: "cooling.csv"      # optional; omit for heating-only scenarios
```

| Field | Default | Notes |
|---|---|---|
| `source` | — | Required. `"csv"` or `"degree_day"`. |
| `ua_kw_per_degC` | — | Required for `degree_day`. Building fabric conductance. |
| `heating_setpoint_c` | `20.0` | Indoor heating setpoint [°C]. |
| `cooling_setpoint_c` | `26.0` | Indoor cooling setpoint [°C]. |
| `heating_csv` | — | Required for `csv` source. Relative to scenario YAML location. |
| `cooling_csv` | `null` | Optional. Omit for heating-only. |

---

### `components.heat_pump`

Air-source heat pump with catalog-based sizing and a temperature-dependent COP.

```yaml
components:
  heat_pump:
    enabled: true
    mode: "both"                    # "heating_only" | "cooling_only" | "both"
    sizing: "catalog_auto"          # "catalog_auto" (smallest model ≥ peak) | "fixed"
    # heating_capacity_kw: 5.0      # required when sizing: "fixed"
    # cooling_capacity_kw: 4.0      # required when sizing: "fixed"
    cop_source: "catalog"           # "catalog" | "fixed" | "dataset"
    # fixed_cop_heating: 3.5        # required when cop_source: "fixed" (+ heating)
    # fixed_cop_cooling: 4.0        # required when cop_source: "fixed" (+ cooling)
    # cop_dataset_path: "cop.csv"   # required when cop_source: "dataset"
    capex: 4000.0                   # $/installed unit (whole system)
    opex_per_year: 150.0
    lifetime_years: 15
```

| Field | Default | Notes |
|---|---|---|
| `mode` | `"both"` | Determines which thermal buses are connected. |
| `sizing` | `"catalog_auto"` | `catalog_auto` picks the smallest standard model ≥ peak demand; `fixed` uses the `*_capacity_kw` fields. |
| `cop_source` | `"catalog"` | How hourly COP is computed (see below). |
| `cop_dataset_path` | `null` | CSV of COP rating points; required when `cop_source: "dataset"`. |
| `capex` | `0.0` | Capital cost of the whole HP system. |
| `lifetime_years` | `15` | Used for replacement scheduling. |

**COP sources (`cop_source`):**

- `catalog` (default): a physics-based **Carnot-fraction** COP model evaluated against
  the outdoor temperature, with a Stull (2011) indoor wet-bulb for cooling. Self-contained;
  no data file needed. See the [Thermal Components Guide](thermal-components.md).
- `fixed`: constant COP from `fixed_cop_heating` / `fixed_cop_cooling`.
- `dataset`: COP curves least-squares **fitted from a performance dataset** CSV at
  `cop_dataset_path`. The CSV has a header and the columns
  `outdoor_temp_c,cop_heating,cop_cooling` (a blank cell skips that mode for that row);
  at least two points are needed per mode. A representative example ships at
  `examples/content/cop_ashp_reference.csv`. To source real-population data
  reproducibly, run [`samba fetch-cop-data`](cli-reference.md#samba-fetch-cop-data)
  (e.g. against the NEEP cold-climate ASHP list) — **verify the source's
  redistribution license before committing the result**.

**Added KPIs:** `mean_cop_heating`, `mean_cop_cooling`, `annual_heat_produced_kwh`,
`annual_cool_produced_kwh`, `annual_hp_elec_kwh`.

See [Thermal Components Guide](thermal-components.md) for COP model details.

---

### `components.thermal_storage`

Hot-water buffer tank for thermal energy time-shifting.

```yaml
components:
  thermal_storage:
    capacity_kwh_th: null           # null = LP investment variable; float = fixed [kWh_th]
    capex_per_kwh_th: 20.0          # $/kWh_th installed
    charge_efficiency: 0.98
    discharge_efficiency: 0.98
    loss_rate_per_hour: 0.002       # fractional standby heat loss per hour
    lifetime_years: 20
```

| Field | Default | Notes |
|---|---|---|
| `capacity_kwh_th` | `null` | `null` triggers investment optimisation. |
| `capex_per_kwh_th` | `20.0` | Capital cost per installed kWh_th. |
| `loss_rate_per_hour` | `0.002` | 0.2% → well-insulated tank. |
| `lifetime_years` | `20` | — |

**Added KPIs:** `thermal_storage_capex`, `annual_thermal_storage_cycles`.

---

### `components.gas_supply`

Natural gas boiler/furnace component.

```yaml
components:
  gas_supply:
    boiler_efficiency: 0.85         # LHV thermal efficiency [0–1]
    capex: 2000.0                   # $/unit installation cost
    opex_per_year: 50.0             # $/yr fixed O&M
    lifetime_years: 20
    co2_per_kwh_th_gas: 0.205       # kg CO2 / kWh_th gas (LHV basis)
    rate:
      type: "flat"                  # "flat" | "seasonal" | "tiered"
      rate_per_kwh_th: 0.04
```

**`rate.type` options:**

```yaml
# flat
rate:
  type: "flat"
  rate_per_kwh_th: 0.04

# seasonal
rate:
  type: "seasonal"
  summer_rate_per_kwh_th: 0.035
  winter_rate_per_kwh_th: 0.050
  summer_months: [5, 6, 7, 8, 9, 10]

# tiered (monthly blocks)
rate:
  type: "tiered"
  tiers:
    - limit_kwh_th: 500
      rate_per_kwh_th: 0.03
    - limit_kwh_th: null
      rate_per_kwh_th: 0.045
```

**Added KPIs:** `annual_gas_consumption_kwh_th`, `annual_gas_cost_usd`,
`annual_gas_co2_kg`, `gas_boiler_npc`, `gas_boiler_capex`.

---

### `constraints.thermal_lpsp_max` — v3

Maximum allowable fraction of thermal demand that may go unmet.

```yaml
constraints:
  thermal_lpsp_max: 0.0      # 0.0 = all demand must be met; 0.05 = up to 5% shed
```

When set to `0.0` (default), the LP requires all heating and cooling demand to
be satisfied in every hour. Positive values allow demand shedding and can make
otherwise-infeasible scenarios feasible.

---

### v3 KPIs

The following KPI fields are added to `kpis.json` when thermal components are present:

| KPI | Units | Description |
|---|---|---|
| `annual_heat_produced_kwh` | kWh_th | Total HP heating output |
| `annual_cool_produced_kwh` | kWh_th | Total HP cooling output |
| `mean_cop_heating` | — | Energy-weighted mean COP over heating hours |
| `mean_cop_cooling` | — | Energy-weighted mean COP over cooling hours |
| `annual_heating_demand_kwh_th` | kWh_th | Total heating demand from load profile |
| `annual_cooling_demand_kwh_th` | kWh_th | Total cooling demand from load profile |
| `annual_hp_elec_kwh` | kWh_e | Total HP electricity consumed |
| `thermal_storage_capex` | $ | Capital cost of thermal storage installed |
| `annual_thermal_storage_cycles` | cycles | Equivalent full cycles per year |
| `annual_gas_consumption_kwh_th` | kWh_th | Total gas consumed (LHV) |
| `annual_gas_cost_usd` | $ | Annual gas utility bill |
| `annual_gas_co2_kg` | kg | Annual gas CO₂ emissions |
| `gas_boiler_npc` | $ | Net present cost of gas boiler component |
| `gas_boiler_capex` | $ | Capital cost of gas boiler installation |
| `thermal_lpsp_heating` | fraction | Fraction of heating hours with unmet demand |
| `thermal_lpsp_cooling` | fraction | Fraction of cooling hours with unmet demand |

---

## v4 Schema Additions

### `tariff.demand_charge`

Demand charge on the monthly peak grid import. Modelled inside the LP, so the
solver shaves peaks (e.g. with storage) rather than just being billed for them.

```yaml
tariff:
  demand_charge:
    rate_per_kw_month: 15.0    # $/kW of monthly peak grid import
    hours: [16, 17, 18, 19, 20]   # optional: restrict the peak window (0-23); omit = all hours
```

KPIs: `annual_demand_charge_usd`, `peak_demand_kw_by_month`.

### `tariff.nem`

Annual net-metering / net-billing reconciliation. Each month's net bill
(`bought$ − sold$`) is floored at $0, surplus export credit carries forward (if
`carryover`), and leftover year-end credit is settled by
`annual_excess_credit_fraction`. The export valuation is whatever you set in
`tariff.sell` (retail for net-metering, a lower rate for net-billing).

```yaml
tariff:
  nem:
    mode: "net_metering"             # or "net_billing" (intent/labelling)
    carryover: true                  # roll monthly credit forward
    annual_excess_credit_fraction: 0.0   # 0 = forfeit leftover, 1 = full cash-out
```

KPI: `annual_energy_net_usd`.

### `load.source: "template"`

Built-in load shapes for users without metered data, scaled to an annual total.

```yaml
load:
  source: "template"
  template_name: "commercial"   # residential | commercial | industrial
  annual_kwh: 50000.0
```

### `weather.source: "nsrdb"`

Fetch a year of NSRDB weather from the NREL API (cached locally so runs are
reproducible and offline-repeatable). Requires an API key + email (or
`NREL_API_KEY` / `NREL_API_EMAIL`). Pre-warm with `samba fetch-weather`.

```yaml
weather:
  source: "nsrdb"
  nsrdb_api_key: "..."     # or set $NREL_API_KEY
  nsrdb_email: "you@example.com"   # or set $NREL_API_EMAIL
```

The site is taken from `location.latitude/longitude` and the year from
`project.year`.

### `components.pv` — bifacial

```yaml
components:
  pv:
    module_type: "bifacial"   # default "monofacial"
    bifaciality: 0.7          # rear/front efficiency ratio (0-1)
```

When bifacial, an estimated rear-side ground-reflected gain is added to the POA,
so a higher ground albedo yields more rear gain.

### `components.battery.degradation`

Replaces the fixed `lifetime_years` nameplate with a throughput-based effective
lifetime (drives replacement cadence and economics).

```yaml
components:
  battery:
    degradation:
      calendar_fade_pct_yr: 1.0          # %/yr capacity loss (calendar ageing)
      cycle_fade_pct_per_efc: 0.01       # % loss per equivalent full cycle
      end_of_life_capacity_pct: 80.0     # replace when capacity drops below this
```

KPIs: `annual_throughput_cycles`, `battery_eol_year`.

### `constraints.max_total_emissions_kg`

Hard cap on annual CO₂ (the basis of the epsilon-constraint Pareto method). Caps
the LP-expressible emissions (grid + diesel fuel slope). Sweep it with
`samba pareto --method epsilon`.

```yaml
constraints:
  max_total_emissions_kg: 5000.0
```
