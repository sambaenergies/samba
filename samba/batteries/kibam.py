# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""KiBaM (Kinetic Battery Model) LP approximation and post-solve validator.

Theory
------
The KiBaM two-tank model partitions battery charge into:

* **Q1** -- "available" charge that interacts directly with charge/discharge
  flows.
* **Q2** -- "bound" charge that transfers to Q1 at first-order rate ''k''
  (h-1).

The full two-tank dynamics are non-linear when ''k'' is uncertain, but for
fixed ''k'' and ''dt = 1 h'' all exponent coefficients become constants.
SAMBA uses a **conservative LP approximation**: the effective maximum charge
and discharge C-rates are pre-computed from the KiBaM kinetics at the
worst-case SOC operating point (lowest dischargeable SOC, highest chargeable
SOC).  These C-rates replace the idealized ''c_rate_charge'' and
''c_rate_discharge'' parameters in the oemof ''GenericStorage'' builder.

A post-solve ''validate_kibam_dispatch'' check re-simulates the full two-tank
dynamics using the LP dispatch as input, detecting cases where the LP
approximation was insufficiently conservative (rare for typical lead-acid
parameters, but possible for aggressive dispatch profiles).

Reference: Manwell & McGowan (1993), "Lead acid battery storage model for hybrid
energy systems", *Solar Energy* 50(5), 399-405 (the kinetic battery model).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import oemof.solph as solph

from samba.compiler.annualize import ep_costs as _ep_costs
from samba.compiler.annualize import real_discount_rate as _real_rate

if TYPE_CHECKING:
    from samba.scenario.models import KiBaMParams, Scenario

log = logging.getLogger(__name__)

__all__ = [
    "KiBaMValidationResult",
    "build_kibam_storage",
    "compute_kibam_limits",
    "validate_kibam_dispatch",
]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class KiBaMValidationResult:
    """Result of KiBaM two-tank post-solve feasibility check.

    Attributes
    ----------
    feasible:
        ''True'' when Q1 >= 0 at every timestep (LP approximation was
        conservative enough).
    n_violations:
        Number of timesteps where Q1 < 0 (available tank went negative).
    worst_q1_deficit_kwh:
        Most negative Q1 observed [kWh]; 0.0 when feasible.
    q1:
        Available-tank energy [kWh] at each of the 8 760 timesteps.
    q2:
        Bound-tank energy [kWh] at each of the 8 760 timesteps.
    soc:
        State-of-charge fraction (Q1 + Q2) / capacity_kwh at each timestep.
    """

    feasible: bool
    n_violations: int
    worst_q1_deficit_kwh: float
    q1: np.ndarray = field(repr=False)
    q2: np.ndarray = field(repr=False)
    soc: np.ndarray = field(repr=False)


# ---------------------------------------------------------------------------
# Kinetic limit computation
# ---------------------------------------------------------------------------


def compute_kibam_limits(
    kibam: KiBaMParams,
    capacity_kwh: float,
    soc_min: float,
    soc_max: float,
    dt_h: float = 1.0,
) -> dict[str, float]:
    """Pre-compute conservative LP C-rate limits from KiBaM kinetics.

    Evaluates:

    * **Discharge limit** at ''soc_min + 0.1*(soc_max - soc_min)'' -- the
      most restrictive low-SOC operating point (Q1 is smallest here).
    * **Charge limit** at ''soc_max - 0.1*(soc_max - soc_min)'' -- the most
      restrictive high-SOC operating point (headroom is smallest here).

    The steady-state assumption Q1 = c*Qt is used when evaluating at a given
    SOC (before any dynamic transient).

    Parameters
    ----------
    kibam:
        KiBaM kinetic parameters from the scenario.
    capacity_kwh:
        Total usable battery capacity [kWh].
    soc_min, soc_max:
        Operating SOC limits (fractions, 0-1).
    dt_h:
        Timestep duration [h]; typically 1.0 for hourly simulation.

    Returns
    -------
    dict with keys:

    * ''c_rate_dch_limit'' -- max discharge as fraction of capacity per hour
    * ''c_rate_ch_limit''  -- max charge as fraction of capacity per hour
    * ''pdch_max_kw''      -- absolute discharge limit [kW]
    * ''pch_max_kw''       -- absolute charge limit [kW]
    """
    c = kibam.c_ratio
    k = kibam.k_rate
    exp_k_dt = math.exp(-k * dt_h)
    # Shared denominator of the Manwell-McGowan max-power expression
    denom = 1.0 - exp_k_dt + c * (k * dt_h - 1.0 + exp_k_dt)

    # ------------------------------------------------------------------
    # Discharge limit (worst-case: low SOC, Q1 = c*Qt at steady state)
    # ------------------------------------------------------------------
    soc_dch = soc_min + 0.1 * (soc_max - soc_min)
    qt_dch = soc_dch * capacity_kwh
    # Manwell-McGowan max discharge power; at the steady-state partition Q1 = c*Qt
    # this reduces to k*c*Qt / denom.
    pdch_max = k * c * qt_dch / denom

    # ------------------------------------------------------------------
    # Charge limit (worst-case: high SOC, Q1 = c*Qt at steady state)
    # Pch_max1 = kinetic (Manwell-McGowan, simplified with Q1=c*Qt):
    #   = k*c*(Qmax - Qt) / denom
    # Pch_max2 = charge acceptance: (1 - exp(-alfa*dt)) * (Qmax - Qt) / dt
    # Pch_max3 = max current: I_max * V_nom / 1000
    # ------------------------------------------------------------------
    soc_ch = soc_max - 0.1 * (soc_max - soc_min)
    qt_ch = soc_ch * capacity_kwh
    qmax = capacity_kwh
    delta_q = qmax - qt_ch  # remaining headroom

    pch_kinetic = k * c * delta_q / denom
    pch_accept = (1.0 - math.exp(-kibam.charge_acceptance * dt_h)) * delta_q / dt_h
    pch_current = kibam.max_charge_current_a * kibam.nominal_voltage_v / 1000.0
    pch_max = min(pch_kinetic, pch_accept, pch_current)

    # Guard against degenerate values (e.g. fully-charged or zero capacity)
    pdch_max = max(pdch_max, 0.0)
    pch_max = max(pch_max, 0.0)

    return {
        "c_rate_dch_limit": pdch_max / capacity_kwh if capacity_kwh > 0.0 else 0.0,
        "c_rate_ch_limit": pch_max / capacity_kwh if capacity_kwh > 0.0 else 0.0,
        "pdch_max_kw": pdch_max,
        "pch_max_kw": pch_max,
    }


# ---------------------------------------------------------------------------
# oemof storage builder
# ---------------------------------------------------------------------------


def build_kibam_storage(scenario: Scenario, dc_bus: solph.Bus) -> solph.components.GenericStorage:
    """Build a ''GenericStorage'' on *dc_bus* using KiBaM-derived C-rate limits.

    Delegates all oemof-solph wiring to a ''GenericStorage'' identical in
    structure to the Li-ion builder, but with charge/discharge flow bounds
    derived from :func:'compute_kibam_limits' rather than the idealized
    ''c_rate_charge'' / ''c_rate_discharge'' scenario parameters.

    Parameters
    ----------
    scenario:
        Validated scenario; ''scenario.components.battery.chemistry''
        must be ''"kibam"''.
    dc_bus:
        DC system bus -- both charge and discharge connect here.

    Returns
    -------
    solph.components.GenericStorage
        Ready to be added to the ''EnergySystem''.
    """
    bat = scenario.components.battery
    if bat is None:
        raise ValueError("build_kibam_storage called but scenario.components.battery is None")
    if bat.kibam is None:
        raise ValueError("build_kibam_storage called but battery.kibam params are None")

    proj = scenario.project
    effective_capex = bat.capex_per_kwh * (1.0 - proj.re_incentive_rate)

    # Use a reference capacity to evaluate kinetic limits.
    # For Investment mode (capacity_kwh=None), use a nominal 10 kWh reference;
    # the resulting C-rate fractions are capacity-independent for the LP.
    ref_cap = bat.capacity_kwh if bat.capacity_kwh is not None else 10.0
    limits = compute_kibam_limits(bat.kibam, ref_cap, bat.soc_min, bat.soc_max)

    # Clamp KiBaM-derived C-rates against user-specified limits (user may
    # provide more conservative bounds for safety margin)
    c_rate_dch = min(limits["c_rate_dch_limit"], bat.c_rate_discharge)
    c_rate_ch = min(limits["c_rate_ch_limit"], bat.c_rate_charge)

    log.debug(
        "KiBaM limits: c_rate_dch=%.4f/h  c_rate_ch=%.4f/h  (idealized: dch=%.4f  ch=%.4f)",
        c_rate_dch,
        c_rate_ch,
        bat.c_rate_discharge,
        bat.c_rate_charge,
    )

    if bat.capacity_kwh is None:
        # ------- Investment mode -------
        r_real = _real_rate(proj.discount_rate_nominal, proj.inflation_rate)
        annual_cost = _ep_costs(effective_capex, r_real, bat.lifetime_years)
        storage: solph.components.GenericStorage = solph.components.GenericStorage(
            label="battery",
            inputs={dc_bus: solph.Flow(nominal_capacity=solph.Investment())},
            outputs={dc_bus: solph.Flow(nominal_capacity=solph.Investment())},
            nominal_capacity=solph.Investment(ep_costs=annual_cost),
            invest_relation_input_capacity=c_rate_ch,
            invest_relation_output_capacity=c_rate_dch,
            inflow_conversion_factor=bat.charge_efficiency,
            outflow_conversion_factor=bat.discharge_efficiency,
            min_storage_level=bat.soc_min,
            max_storage_level=bat.soc_max,
            initial_storage_level=bat.soc_initial,
        )
        log.debug("KiBaM battery: Investment mode -- ep_costs=%.4f $/kWh/yr", annual_cost)
    else:
        # ------- Fixed capacity mode -------
        charge_kw = bat.capacity_kwh * c_rate_ch
        discharge_kw = bat.capacity_kwh * c_rate_dch
        storage = solph.components.GenericStorage(
            label="battery",
            inputs={dc_bus: solph.Flow(nominal_capacity=charge_kw)},
            outputs={dc_bus: solph.Flow(nominal_capacity=discharge_kw)},
            nominal_capacity=bat.capacity_kwh,
            inflow_conversion_factor=bat.charge_efficiency,
            outflow_conversion_factor=bat.discharge_efficiency,
            min_storage_level=bat.soc_min,
            max_storage_level=bat.soc_max,
            initial_storage_level=bat.soc_initial,
        )
        log.debug(
            "KiBaM battery: Fixed mode -- capacity=%.2f kWh  charge_kw=%.3f  discharge_kw=%.3f",
            bat.capacity_kwh,
            charge_kw,
            discharge_kw,
        )

    return storage


# ---------------------------------------------------------------------------
# Post-solve two-tank validator
# ---------------------------------------------------------------------------


def validate_kibam_dispatch(
    dispatch_kw: np.ndarray,
    capacity_kwh: float,
    kibam: KiBaMParams,
    soc_initial: float,
    dt_h: float = 1.0,
) -> KiBaMValidationResult:
    """Re-simulate KiBaM two-tank dynamics using LP dispatch as input.

    Uses the Manwell-McGowan kinetic-battery equations to propagate Q1 and Q2.
    Detects timesteps where the available tank (Q1) goes negative -- an
    infeasibility that the LP approximation allowed but the physical model
    would not.

    Parameters
    ----------
    dispatch_kw:
        Net dispatch power [kW] at each timestep: **positive = discharge,
        negative = charge**.  Shape ''(T,)''.
    capacity_kwh:
        Total usable battery capacity [kWh].
    kibam:
        KiBaM kinetic parameters.
    soc_initial:
        Initial state of charge fraction (0-1).
    dt_h:
        Timestep duration [h]; typically 1.0.

    Returns
    -------
    KiBaMValidationResult
    """
    c = kibam.c_ratio
    k = kibam.k_rate
    n = len(dispatch_kw)
    exp_k_dt = math.exp(-k * dt_h)

    q1_arr = np.empty(n, dtype=np.float64)
    q2_arr = np.empty(n, dtype=np.float64)
    soc_arr = np.empty(n, dtype=np.float64)

    # Initial conditions: assume steady-state partition
    qt_init = soc_initial * capacity_kwh
    q1_t = c * qt_init
    q2_t = (1.0 - c) * qt_init

    n_violations = 0
    worst_q1_deficit = 0.0

    # ramp term (k*dt - 1 + e^{-k*dt}) / k, shared by both tank updates
    ramp = (k * dt_h - 1.0 + exp_k_dt) / k

    for t in range(n):
        q0 = q1_t + q2_t  # total stored charge (available + bound)
        p = dispatch_kw[t]  # positive = discharge

        # Canonical kinetic-battery two-tank charge evolution under constant power
        # over one step, tracking the available (q1) and bound (q2) tanks
        # separately -- Manwell & McGowan (1993), *Solar Energy* 50(5), 399-405.
        q1_next = q1_t * exp_k_dt + ((q0 * k * c - p) * (1.0 - exp_k_dt)) / k - p * c * ramp
        q2_next = q2_t * exp_k_dt + q0 * (1.0 - c) * (1.0 - exp_k_dt) - p * (1.0 - c) * ramp

        q1_arr[t] = q1_next
        q2_arr[t] = q2_next
        soc_arr[t] = (q1_next + q2_next) / capacity_kwh if capacity_kwh > 0.0 else 0.0

        if q1_next < -1e-6:
            n_violations += 1
            if q1_next < worst_q1_deficit:
                worst_q1_deficit = q1_next

        # Clamp to zero to prevent runaway negative values
        q1_t = max(q1_next, 0.0)
        q2_t = max(q2_next, 0.0)

    return KiBaMValidationResult(
        feasible=n_violations == 0,
        n_violations=n_violations,
        worst_q1_deficit_kwh=worst_q1_deficit,
        q1=q1_arr,
        q2=q2_arr,
        soc=soc_arr,
    )
