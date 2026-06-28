# Known Limitations

This document describes what SAMBA does and does **not** model as of the current
release (v5.3.0). It reflects features that have actually shipped — earlier
releases deferred many items (EV, thermal, demand charges, bifacial PV, NSRDB
fetch, …) that are now implemented; see the [CHANGELOG](../CHANGELOG.md) for the
per-version history.

---

## Modelling resolution

| Limitation | Detail |
|---|---|
| Single representative year | Dispatch is optimised over one 8760-hour year. Long-run capacity fade is approximated via battery degradation + replacement scheduling, not a multi-year rolling simulation. |
| Hourly resolution | All flows are hourly. Sub-hourly ramp rates, frequency response, and reserve products are not modelled. |
| Single load bus | Electrical loads are aggregated onto one AC node; thermal loads onto heating/cooling buses. Individual interruptible/shiftable load blocks are not separated. |

---

## Optimisation

| Capability | Status / caveat |
|---|---|
| Objective | Minimise NPC (default), or NPC + weighted emissions (`objective.type: cost_and_emissions`). |
| Multi-objective Pareto | `samba pareto` supports two methods. `--method weighted_sum` (default) is fast but only recovers points on the **convex hull** of the true frontier. `--method epsilon` (epsilon-constraint) captures non-convex regions at the cost of extra solves. |
| Diesel unit commitment | `min_up_hours`, `min_down_hours`, and `startup_cost` are modelled as a MILP and solve over the full 8760-h horizon. The **intercept** term of the fuel curve (`intercept_l_per_kw_hr`, fixed litres per operating hour) is accounted for in post-processing rather than in the LP objective, to avoid bilinear terms — so per-hour fuel **cost is slightly underestimated at part load**. The slope (variable) term is exact. |
| Fuel curve shape | Linear (affine) only; quadratic / piecewise fuel curves are not supported. |

---

## Weather and irradiance

| Limitation | Detail |
|---|---|
| Isotropic transposition only | Plane-of-array irradiance uses [pvlib](https://pvlib-python.readthedocs.io) (NREL SPA solar position + an **isotropic** sky-diffuse transposition). Anisotropic models (Hay-Davies, Perez) are not currently exposed. |
| NSRDB-format input | `weather.source: csv` expects an NSRDB-format file (header rows + 8760 data rows with GHI/DNI/DHI/temperature/wind). `weather.source: nsrdb` fetches from the NREL NSRDB API (`samba fetch-weather`); other formats need manual preprocessing. |
| No soiling-loss field | PV losses are a single `derating_factor` multiplier; soiling, shading, and mismatch must be pre-combined into it. |

---

## Battery

| Limitation | Detail |
|---|---|
| KiBaM solved as an LP relaxation | The two-tank kinetic (lead-acid) model is solved as an **LP relaxation** of the non-linear kinetics. A post-solve check (`validate_kibam_dispatch`) re-simulates the schedule and may flag a small, bounded number of timesteps (typically ≤ 10) where the LP allowed slightly more discharge than the kinetic model sustains near low SOC. These are logged as a warning and do not affect LPSP. Set `SolverConfig(strict_kibam=True)` to turn them into a hard `ConstraintViolationError`. |
| Degradation granularity | Capacity fade (throughput + calendar) derives an effective lifetime that drives replacement economics; it is not modelled as continuous hourly capacity loss within a year. |
| Single pack per scenario | One battery pack/chemistry per scenario; comparing chemistries requires separate scenarios. |

---

## Thermal (heat pump / storage / gas)

| Limitation | Detail |
|---|---|
| Physics-based, size-independent COP | Heat-pump COP is a physics-based **Carnot-fraction** model (Carnot limit × a practical second-law efficiency) with a Stull (2011) wet-bulb. It is intentionally simplified and **not** fitted to manufacturer catalog curves, so it is less catalog-accurate than a vendor regression and does not vary with unit size. See [`thermal-components.md`](thermal-components.md). |
| Merit-order thermal dispatch | HP vs gas boiler is chosen by LP merit order on hourly prices; no thermal network losses or pipe dynamics are modelled. |
| No hydrogen / district energy | Hydrogen systems and district heating/cooling networks are out of scope. |

---

## Tariffs and grid accounting

| Capability | Status / caveat |
|---|---|
| NEM reconciliation | `tariff.nem` models monthly `$0`-floored bills with export-credit carryover and year-end settlement. Without it, grid cost is the full bilateral present-value cashflow (`bought × cbuy − sold × csell + service`, all × PWF), which shows a higher NPC for net-exporting systems than a NEM-floored utility would bill. |
| Demand charges | `tariff.demand_charge` models `$/kW-month` on the monthly peak grid import inside the LP (the solver shaves peaks). |
| Tiered rates | Endogenous tiering (`endogenous_tiering: true`) enforces monthly consumption against tier limits inside the LP. The non-endogenous path pre-computes a per-hour rate array held constant through the solve (an approximation). |
| Grid tax / surcharges | No separate system tax or per-kWh surcharge field; fold these into an effective `buy` rate if needed. |

---

## Economics

| Limitation | Detail |
|---|---|
| Single-point replacement | Components are replaced at integer multiples of their lifetime; partial within-period degradation is not separately costed. |
| Real cashflows | Cashflows use the real discount rate; nominal escalation is supported on grid costs via `grid_escalation_rate`. |

---

## Emissions

| Limitation | Detail |
|---|---|
| User-supplied factors | Emission factors (`dg_emissions_kg_per_l`, `grid_emissions_kg_per_kwh`, gas LHV CO₂) are user inputs; SAMBA does not fetch real-time marginal grid emission rates. |
| Optional in objective | Emissions are always reported as KPIs; they enter the objective only under `objective.type: cost_and_emissions` or the Pareto sweep. |

---

## Interfaces

| Limitation | Detail |
|---|---|
| REST job store | `samba_service` exposes async job endpoints. The job store is in-process by default (records lost on restart); set `SAMBA_PERSIST_JOBS` for a SQLite-backed store that survives restarts. See [`deployment.md`](deployment.md). |
| UI packaging | The `ui/` directory is a working Vue 3 + Tauri front-end (web + desktop dev modes), driven by types generated from the backend schema. Native installers that bundle the backend (no Python required) are not yet shipped. |
