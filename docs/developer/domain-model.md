# Domain Model

This document defines every energy system component SAMBA supports, its physical model, parameters, economic model, and how it maps to an oemof-solph construct. This is the binding reference for implementation.

## Timebase Convention

- **Timestep:** 1 hour
- **Horizon:** 8760 hours (one non-leap year)
- **Leap year policy:** Ignored. Always 8760 timesteps. Leap year days are dropped if present in input data.
- **Index convention:** 0-based (hour 0 = Jan 1, 00:00)
- **Timezone:** All input data must be in local time. SAMBA does not perform timezone conversion.

## Bus Architecture

SAMBA models energy flows through buses. The v1 electrical system has two buses:

```
[PV] ──→ DC Bus ──→ [Inverter] ──→ AC Bus ──→ [Load]
                         ↕                ↕
                    [Battery]         [Grid Buy/Sell]
                                          ↕
[Wind Turbine] ──────────────────────→ AC Bus
[Diesel Generator] ──────────────────→ AC Bus
```

| Bus    | oemof construct | Notes                                |
| ------ | --------------- | ------------------------------------ |
| DC Bus | `solph.Bus`     | PV output and battery are DC-coupled |
| AC Bus | `solph.Bus`     | Load, grid, DG, and WT connect here  |

The inverter bridges DC↔AC. The solver respects the inverter capacity constraint and efficiency in both directions.

---

## Components

### 1. Photovoltaic (PV)

**Physical model:**

PV output is computed outside oemof as a pre-processed hourly time series fed to a Source with `Investment`.

Cell temperature (NOCT model):

$$T_c = \frac{T_a + 273.15 + (T_{c,NOCT} - T_{a,NOCT}) \cdot \frac{G}{G_{NOCT}} \cdot \left(1 - \frac{\eta_{PV} \cdot (1 - \frac{T_{cof}}{100} \cdot (T_{ref} + 273.15))}{\gamma}\right)}{1 + (T_{c,NOCT} - T_{a,NOCT}) \cdot \frac{G}{G_{NOCT}} \cdot \frac{\frac{T_{cof}}{100} \cdot \eta_{PV}}{\gamma}}$$

Output power per kW rated:

$$P_{pv,norm} = f_{pv} \cdot \frac{G}{G_{ref}} \cdot \left(1 + \frac{T_{cof}}{100} \cdot (T_c - 273.15 - T_{ref})\right)$$

The total PV output is $P_{pv} = N_{pv} \cdot P_{pv,r} \cdot P_{pv,norm}$, but in SAMBA the solver determines $N_{pv}$ (or equivalently, total kW capacity) via the investment optimization.

**Parameters:**

| Parameter                | Symbol       | Unit  | Default | Notes                                        |
| ------------------------ | ------------ | ----- | ------------ | -------------------------------------------- |
| Derating factor          | $f_{pv}$     | —     | 0.9          | Accounts for wiring, mismatch, shading       |
| Temperature coefficient  | $T_{cof}$    | %/°C  | -0.3         | Negative = output decreases with temperature |
| Reference temperature    | $T_{ref}$    | °C    | 25           | STC reference                                |
| NOCT cell temperature    | $T_{c,NOCT}$ | °C    | 45           |                                              |
| NOCT ambient temperature | $T_{a,NOCT}$ | °C    | 20           |                                              |
| NOCT irradiance          | $G_{NOCT}$   | W/m²  | 800          |                                              |
| Absorption coefficient   | $\gamma$     | —     | 0.9          |                                              |
| Module efficiency        | $\eta_{PV}$  | —     | 0.2182       |                                              |
| Reference irradiance     | $G_{ref}$    | W/m²  | 1000         | STC                                          |
| Panel area per kW        | —            | m²/kW | 5            | For rooftop constraint                       |
| Rated power per unit     | $P_{pv,r}$   | kW    | 1            |                                              |

**oemof mapping:** `solph.components.Source` on DC bus with `fix` (normalized hourly output) and `Investment(ep_costs=..., maximum=...)`. The `maximum` enforces capacity caps (rooftop area, NEM limits).

**Economic model:**

| Parameter              | Symbol    | Unit    | Default |
| ---------------------- | --------- | ------- | ------------ |
| Capital cost           | $C_{PV}$  | $/kW    | 338          |
| Replacement cost       | $R_{PV}$  | $/kW    | 338          |
| O&M cost               | $MO_{PV}$ | $/kW/yr | 30.36        |
| Lifetime               | $L_{PV}$  | years   | 25           |
| Engineering/soft costs | $C_{eng}$ | $/kW    | 2030         |
| RE incentive (ITC)     | —         | %       | 30           |

---

### 2. Wind Turbine (WT)

**Physical model:**

Hub-height wind speed adjustment:

$$v_{hub} = v_{ref} \cdot \left(\frac{h_{hub}}{h_0}\right)^{\alpha}$$

Power output (cubic interpolation between cut-in and rated):

$$P_{wt} = \begin{cases} 0 & v_{hub} < v_{ci} \\ P_{r} \cdot \frac{v_{hub}^3 - v_{ci}^3}{v_{r}^3 - v_{ci}^3} & v_{ci} \leq v_{hub} < v_r \\ P_r & v_r \leq v_{hub} < v_{co} \\ 0 & v_{hub} \geq v_{co} \end{cases}$$

**Parameters:**

| Parameter            | Symbol     | Unit | Default |
| -------------------- | ---------- | ---- | ------------ |
| Hub height           | $h_{hub}$  | m    | 17           |
| Anemometer height    | $h_0$      | m    | 43.6         |
| Friction coefficient | $\alpha$   | —    | 0.14         |
| Cut-in speed         | $v_{ci}$   | m/s  | 2.5          |
| Cut-out speed        | $v_{co}$   | m/s  | 25           |
| Rated speed          | $v_r$      | m/s  | 9.5          |
| Rated power per unit | $P_{wt,r}$ | kW   | 1            |

**oemof mapping:** `solph.components.Source` on AC bus with `fix` (normalized hourly output) and `Investment(ep_costs=...)`.

**Economic model:**

| Parameter        | Symbol    | Unit    | Default |
| ---------------- | --------- | ------- | ------------ |
| Capital cost     | $C_{WT}$  | $/kW    | 1200         |
| Replacement cost | $R_{WT}$  | $/kW    | 1200         |
| O&M cost         | $MO_{WT}$ | $/kW/yr | 40           |
| Lifetime         | $L_{WT}$  | years   | 20           |

---

### 3. Battery Energy Storage (Li-ion)

**Physical model:**

SAMBA uses an idealized battery model for Li-ion. The key dynamics are:

State of energy update:

$$E_b(t+1) = (1 - \sigma) \cdot E_b(t) + P_{ch}(t) \cdot \sqrt{\eta} \cdot \Delta t - \frac{P_{dch}(t)}{\sqrt{\eta}} \cdot \Delta t$$

Maximum charge power:

$$P_{ch,max} = \min\left(\frac{(1 - e^{-\alpha \Delta t})(E_{max} - E_b)}{\Delta t \cdot \sqrt{\eta}}, \quad \frac{N_{bat} \cdot I_{ch,max} \cdot V_{nom}}{1000 \cdot \sqrt{\eta}}, \quad \frac{SOC_{max} \cdot C_n - E_b}{\Delta t \cdot \sqrt{\eta}}\right)$$

Maximum discharge power:

$$P_{dch,max} = \frac{N_{bat} \cdot I_{dch,max} \cdot V_{nom} \cdot \sqrt{\eta}}{1000}$$

Battery wear cost:

$$C_{bw} = \frac{R_B \cdot C_n}{N_{bat} \cdot Q_{lifetime} \cdot \sqrt{\eta}}$$

**Parameters:**

| Parameter               | Symbol          | Unit | Default |
| ----------------------- | --------------- | ---- | ------------ |
| Max charge current      | $I_{ch,max}$    | A    | 167          |
| Max discharge current   | $I_{dch,max}$   | A    | 500          |
| Nominal voltage         | $V_{nom}$       | V    | 6            |
| Nominal capacity        | $C_{nom}$       | Ah   | 167          |
| Charge rate factor      | $\alpha$        | A/Ah | 1            |
| Round-trip efficiency   | $\eta$          | —    | 0.90         |
| Lifetime throughput     | $Q_{lifetime}$  | kWh  | 3000         |
| SOC min                 | $SOC_{min}$     | —    | 0.1          |
| SOC max                 | $SOC_{max}$     | —    | 1.0          |
| SOC initial             | $SOC_{initial}$ | —    | 0.5          |
| Self-discharge rate     | $\sigma$        | /hr  | 0            |
| Rated capacity per unit | $C_{bt,r}$      | kWh  | 1.002        |

**oemof mapping:** `solph.components.GenericStorage` on DC bus with `Investment`. Key parameters map as:

| SAMBA parameter       | oemof parameter                                          |
| --------------------- | -------------------------------------------------------- |
| $\eta$ (split)        | `inflow_conversion_factor`, `outflow_conversion_factor`  |
| $SOC_{min}$           | `min_storage_level`                                      |
| $SOC_{max}$           | `max_storage_level`                                      |
| $SOC_{initial}$       | `initial_storage_level`                                  |
| $\sigma$              | `loss_rate`                                              |
| Capacity (investment) | `Investment(ep_costs=...)` on `nominal_storage_capacity` |

**Note:** oemof's `GenericStorage` handles dispatch optimally — the solver determines when to charge/discharge, with no priority-based heuristic.

**Economic model:**

| Parameter        | Symbol | Unit     | Default |
| ---------------- | ------ | -------- | ------------ |
| Capital cost     | $C_B$  | $/kWh    | 1450         |
| Replacement cost | $R_B$  | $/kWh    | 1450         |
| O&M cost         | $MO_B$ | $/kWh/yr | 10           |
| Lifetime         | $L_B$  | years    | 10           |

---

### 4. Diesel Generator (DG)

**Physical model:**

Fuel consumption (linear model):

$$q(t) = a \cdot P_{dg}(t) + b \cdot P_{n,DG} \quad \text{[L/hr], when } P_{dg}(t) > 0$$

Minimum load ratio constraint:

$$P_{dg}(t) \geq LR_{DG} \cdot P_{n,DG} \quad \text{when operating}$$

**Parameters:**

| Parameter               | Symbol     | Unit           | Default |
| ----------------------- | ---------- | -------------- | ------------ |
| Fuel curve slope        | $a$        | L/hr/kW output | 0.4388       |
| Fuel curve intercept    | $b$        | L/hr/kW rated  | 0.1097       |
| Minimum load ratio      | $LR_{DG}$  | —              | 0.25         |
| Operating lifetime      | $TL_{DG}$  | hours          | 24000        |
| Rated capacity per unit | $C_{dg,r}$ | kW             | 5.5          |

**Emissions per liter of fuel:**

| Emission | Factor | Unit |
| -------- | ------ | ---- |
| CO2      | 2.29   | kg/L |
| NOx      | 0      | kg/L |
| SO2      | 0      | kg/L |

**oemof mapping:** This requires careful modeling because of the min-load constraint and fuel consumption:

- **Fuel bus** (`solph.Bus`): Represents diesel fuel supply.
- **Fuel source** (`solph.components.Source`): Connects to fuel bus with variable cost = $C_{fuel}$.
- **Generator** (`solph.components.Converter`): Fuel bus → AC bus, with `Investment` on output flow. The conversion factor encodes the fuel curve.
- **Min load constraint:** Enforced via `min` parameter on the output `Flow`, or via `NonConvex` flow with `minimum` parameter. Requires MILP (binary on/off variable).

**Economic model:**

| Parameter        | Symbol     | Unit    | Default |
| ---------------- | ---------- | ------- | ------------ |
| Capital cost     | $C_{DG}$   | $/kW    | 818          |
| Replacement cost | $R_{DG}$   | $/kW    | 818          |
| O&M cost         | $MO_{DG}$  | $/op.hr | 0.016        |
| Fuel cost        | $C_{fuel}$ | $/L     | 1.281        |
| Fuel escalation  | —          | %/yr    | 2            |

---

### 5. Inverter / Converter

**Physical model:**

Simple efficiency model for DC↔AC conversion:

$$P_{AC} = \eta_I \cdot P_{DC}$$

DC/AC ratio constraint limits how much DC capacity can feed through the inverter:

$$\frac{P_{DC,rated}}{P_{AC,rated}} \leq DC\_AC\_ratio$$

**Parameters:**

| Parameter         | Symbol   | Unit  | Default |
| ----------------- | -------- | ----- | ------------ |
| Efficiency        | $\eta_I$ | —     | 0.96         |
| DC/AC ratio limit | —        | —     | 1.99         |
| Lifetime          | $L_I$    | years | 25           |

**oemof mapping:** `solph.components.Converter` (bidirectional) between DC bus and AC bus with `Investment(ep_costs=...)`. Conversion factor = $\eta_I$ in both directions.

**Economic model:**

| Parameter        | Symbol | Unit    | Default |
| ---------------- | ------ | ------- | ------------ |
| Capital cost     | $C_I$  | $/kW    | 314          |
| Replacement cost | $R_I$  | $/kW    | 314          |
| O&M cost         | $MO_I$ | $/kW/yr | 0            |

---

### 6. Grid Connection

**Physical model:**

The grid is modeled as an infinite source/sink with:

- Maximum buy power: $P_{buy,max}$
- Maximum sell power: $P_{sell,max}$
- Time-varying buy price: $C_{buy}(t)$ (8760 array from tariff calculator)
- Time-varying sell price: $C_{sell}(t)$ (8760 array)

**Parameters:**

| Parameter      | Symbol         | Unit | Default |
| -------------- | -------------- | ---- | ------------ |
| Max buy power  | $P_{buy,max}$  | kW   | 50           |
| Max sell power | $P_{sell,max}$ | kW   | 50           |
| Grid enabled   | —              | bool | true         |
| NEM enabled    | —              | bool | true         |
| NEM setup fee  | —              | $    | 0            |

**Grid emissions:**

| Emission | Factor | Unit   |
| -------- | ------ | ------ |
| CO2      | 0      | kg/kWh |
| SO2      | 0      | kg/kWh |
| NOx      | 0      | kg/kWh |

**oemof mapping:**

- **Grid buy:** `solph.components.Source` → AC bus, with `variable_costs = Cbuy(t)` and `nominal_value = Pbuy_max`.
- **Grid sell:** AC bus → `solph.components.Sink`, with `variable_costs = -Csell(t)` (negative = revenue) and `nominal_value = Psell_max`.

**NEM handling:** Net energy metering with annual credit reconciliation is modeled as a post-processing step on the optimization results (constraint that net annual grid cost ≥ 0), or as an annual balancing constraint in the oemof model.

---

### 7. Electrical Load

**Physical model:**

Fixed demand sink. The load profile is a pre-processed 8760-element array in kWh.

**Input methods:**

1. Hourly CSV (8760 values)
2. Monthly hourly averages (12 values, expanded)
3. Monthly daily averages (12 values, expanded)
4. Monthly totals (12 values, expanded)
5. Scaled generic load from monthly totals
6. Annual hourly average (single value)
7. Annual daily average (single value)
8. Scaled generic load from annual total
9. Generic load profile (unscaled)
10. Daily load profile CSV (365 values, expanded)

**oemof mapping:** `solph.components.Sink` on AC bus with `fix` (normalized hourly demand) and `nominal_value = peak_load`. Unmet load is modeled via a shortage `Source` with high variable cost.

---

## Economic Framework

The economic model operates over a `n`-year project lifetime (default: 25 years) with the following structure:

### Net Present Cost (NPC)

$$NPC = \left(I_{cost} + \sum R_{cost} + \sum MO_{cost} + \sum C_{fuel} - Salvage\right) \cdot (1 + Tax_{sys}) + \sum Grid_{cost,net}$$

Where:

- $I_{cost}$: Total investment cost (with ITC subtracted from renewable components)
- $R_{cost}$: Replacement costs, discounted, computed at 1/10-year resolution for fractional lifetimes
- $MO_{cost}$: Annual O&M, discounted
- $C_{fuel}$: DG fuel cost with annual escalation, discounted
- $Salvage$: Remaining value of components at end of project life
- $Grid_{cost,net}$: Annual grid buy cost minus sell revenue, with escalation, taxes, credits

### Levelized Cost of Energy (LCOE)

$$LCOE = \frac{CRF \cdot NPC}{E_{tot}}$$

Where $CRF = \frac{ir \cdot (1+ir)^n}{(1+ir)^n - 1}$ and $E_{tot} = \sum(E_{load} - E_{ns} + P_{sell})$.

### Levelized Emissions (LEM)

$$LEM = \frac{DG_{emissions} + Grid_{emissions}}{\sum(E_{load} - E_{ns} + P_{sell})}$$

### Discount Rate

Real discount rate from nominal and inflation:

$$ir = \frac{ir_{nominal} - ir_{inflation}}{1 + ir_{inflation}}$$

### Replacement Scheduling

Replacements are computed at 1/10-year resolution. For a component with lifetime $L$, replacements occur at years $L, 2L, 3L, ...$ up to year $n$. Each replacement is discounted to present value. The number of replacements is $RT = \lceil n/L \rceil - 1$.

### Salvage Value

For each component, the remaining life at end of project:

$$L_{rem} = (RT + 1) \cdot L - n$$
$$S = R_{cost} \cdot Capacity \cdot \frac{L_{rem}}{L} \cdot \frac{1}{(1+ir)^n}$$

---

## Tariff / Rate Structure System

SAMBA supports 8 electricity rate structures. Each is a function that produces an 8760-element `Cbuy` array ($/kWh per hour):

| ID  | Type              | Key Inputs                                                                       |
| --- | ----------------- | -------------------------------------------------------------------------------- |
| 1   | Flat              | Single price                                                                     |
| 2   | Seasonal          | Summer/winter prices, season map                                                 |
| 3   | Monthly           | 12 monthly prices                                                                |
| 4   | Tiered            | Tier prices + kWh limits, accumulates monthly                                    |
| 5   | Seasonal tiered   | Season × tier matrix                                                             |
| 6   | Monthly tiered    | Month × tier matrix                                                              |
| 7   | Time-of-use (TOU) | On/mid/off peak prices × season, peak hour definitions, holiday/weekend handling |
| 8   | Ultra-low TOU     | TOU + ultra-low overnight tier                                                   |

The same rate structure system applies to sell rates and (in v2) natural gas rates.

**Service charges** are monthly fixed charges, either flat or tiered based on previous year's peak monthly consumption.

---

## Weather Processing

**POA Irradiance Calculator** (from `sam_monofacial_poa.py`):

- Input: NSRDB-format weather CSV with GHI, DNI, DHI, Temperature, Wind Speed, Pressure, Dew Point, Albedo
- Computes: Solar position (declination, hour angle, zenith, azimuth), surface angles, beam/diffuse/ground-reflected irradiance on tilted surface
- Accounts for: Soiling losses, Fresnel reflection losses
- Output: POA irradiance (W/m²), ambient temperature (°C), wind speed (m/s)

Users can alternatively provide pre-computed hourly arrays directly.

---

## Deferred Components

### EV / V2G (v2)

The EV model covers presence scheduling (home/away), smart charging with price lookahead, a 3-tier V2G discharge strategy, and travel energy depletion. This is significantly complex and is designed as a dedicated component with its own bus and constraints in v2.

### KiBaM Battery (v2)

Lead-acid batteries are modelled with the Kinetic Battery Model (two-tank kinetics; Manwell & McGowan, 1993). This doesn't map cleanly to oemof's GenericStorage, so v2 adds a custom component / linearized approximation.

### DG Unit Commitment (v2)

v1 models basic min load ratio via NonConvex flow. v2 adds min up/down time constraints and start-up costs for realistic genset operational modeling.

### Heat Pump (v3)

Heat pumps are modelled in v3 as a Converter on a thermal bus: a standard nominal model is selected from peak heating/cooling load, and hourly COP is computed from a physics-based (Carnot-fraction) model on outdoor temperature.

### Thermal Domain (v3)

v3 adds:

- Thermal bus (heating)
- Thermal bus (cooling)
- Heat pump: Converter from electrical bus to thermal bus with time-varying COP
- Thermal storage: GenericStorage on thermal bus
- Building thermal loads: Sink on thermal bus(es)
- Natural gas supply: Source on thermal bus with fuel cost
