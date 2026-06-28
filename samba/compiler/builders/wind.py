# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Wind turbine builder and power-curve utilities for oemof-solph.

The builder creates a ''solph.components.Source'' on the AC bus.  Even though
unit count is fixed in v1, the wind capex is injected into the oemof objective
via ''solph.Investment'' with ''maximum = rated_kw * count'' -- this is required
so the optimizer correctly accounts for the capital cost.

Power-curve utility
-------------------
''calc_wind_power_kw'' converts an 8 760-element wind-speed array to an
hourly AC power output per turbine using a simple parametric power curve
(cubic ramp between cut-in and rated speed, flat at rated power, zero above
cut-out).  This function is called by the data-pipeline layer (Phase 5) before
handing the computed array to the compiler.
"""

from __future__ import annotations

import logging

import numpy as np
import oemof.solph as solph

from samba.compiler.annualize import crf as _crf
from samba.compiler.annualize import real_discount_rate as _real_rate
from samba.scenario.models import Scenario

log = logging.getLogger(__name__)

__all__ = ["WindBuilder", "calc_wind_power_kw", "get_turbine_rated_kw"]

# ---------------------------------------------------------------------------
# Internal turbine specification registry
# ---------------------------------------------------------------------------

#: Minimal power-curve parameters for bundled reference turbines.
#: Keys: (cut_in_ms, rated_ms, cut_out_ms, rated_kw)
_TURBINE_SPECS: dict[str, dict[str, float]] = {
    "generic_1kw": {
        "cut_in_ms": 2.5,
        "rated_ms": 12.0,
        "cut_out_ms": 25.0,
        "rated_kw": 1.0,
    },
    "generic_10kw": {
        "cut_in_ms": 2.5,
        "rated_ms": 12.0,
        "cut_out_ms": 25.0,
        "rated_kw": 10.0,
    },
    "generic_100kw": {
        "cut_in_ms": 3.0,
        "rated_ms": 13.0,
        "cut_out_ms": 25.0,
        "rated_kw": 100.0,
    },
    "v80_2000": {
        "cut_in_ms": 4.0,
        "rated_ms": 15.0,
        "cut_out_ms": 25.0,
        "rated_kw": 2000.0,
    },
}


# ---------------------------------------------------------------------------
# Public utilities
# ---------------------------------------------------------------------------


def get_turbine_rated_kw(turbine_model: str) -> float:
    """Return the rated power [kW] for a bundled turbine model.

    Parameters
    ----------
    turbine_model:
        Key in the internal turbine registry (e.g. ''"generic_10kw"'').

    Raises
    ------
    KeyError
        If *turbine_model* is not in the registry.
    """
    if turbine_model not in _TURBINE_SPECS:
        available = ", ".join(sorted(_TURBINE_SPECS))
        raise KeyError(f"Unknown turbine model {turbine_model!r}. Available models: {available}")
    return _TURBINE_SPECS[turbine_model]["rated_kw"]


def calc_wind_power_kw(
    wind_speed_ms: np.ndarray,
    turbine_model: str,
) -> np.ndarray:
    """Compute per-turbine AC power output from hourly wind speed.

    Uses a parametric power curve: cubic ramp from cut-in to rated speed,
    rated power between rated and cut-out, zero otherwise.

    Parameters
    ----------
    wind_speed_ms:
        1-D array of hub-height wind speed in m/s, shape ''(8760,)''.
    turbine_model:
        Turbine key in the internal registry.

    Returns
    -------
    np.ndarray, shape ''(8760,)''
        Per-turbine power output in kW (not normalized).
    """
    spec = _TURBINE_SPECS.get(turbine_model)
    if spec is None:
        raise KeyError(f"Unknown turbine model {turbine_model!r}")

    v_ci = spec["cut_in_ms"]
    v_r = spec["rated_ms"]
    v_co = spec["cut_out_ms"]
    p_r = spec["rated_kw"]

    v = np.asarray(wind_speed_ms, dtype=np.float64)
    power = np.zeros_like(v)

    # Cubic ramp region: cut_in <= v < rated
    ramp = (v >= v_ci) & (v < v_r)
    power[ramp] = p_r * ((v[ramp] - v_ci) / (v_r - v_ci)) ** 3

    # Rated region: rated <= v <= cut_out
    rated_region = (v >= v_r) & (v <= v_co)
    power[rated_region] = p_r

    return power


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class WindBuilder:
    """Builds the oemof wind turbine source node on the DC bus.

    Wind is DC-coupled, so renewable generation is ''P_RE = Ppv + Pwt''.
    Both PV and wind feed the shared DC bus, pass through the inverter together,
    and can charge the battery.  Placing wind on the AC bus (previous behaviour)
    would prevent battery charging from wind surplus.
    """

    def build(
        self,
        scenario: Scenario,
        dc_bus: solph.Bus,
        ac_bus: solph.Bus,
        wind_power_kw: np.ndarray,
    ) -> list[solph.network.Node]:
        """Return a single ''Source'' representing the wind fleet on *dc_bus*.

        Parameters
        ----------
        scenario:
            Validated scenario; ''scenario.components.wind_turbine'' must not
            be ''None''.
        dc_bus:
            DC system bus -- wind source outputs here (DC-coupled).
        ac_bus:
            AC system bus (accepted for protocol compatibility; wind goes to dc_bus).
        wind_power_kw:
            Per-turbine hourly power output in kW (shape ''(8760,)''),
            typically from :func:'calc_wind_power_kw'.

        Returns
        -------
        list containing one :class:'solph.components.Source'
        """
        wt = scenario.components.wind_turbine
        if wt is None:
            raise ValueError(
                "WindBuilder.build called but scenario.components.wind_turbine is None"
            )

        proj = scenario.project
        rated_kw = get_turbine_rated_kw(wt.turbine_model)
        count = wt.count

        # Total fleet power and normalized profile
        total_wind_kw = wind_power_kw * float(count)
        max_rated_kw = rated_kw * float(count)

        # Normalize to [0,1] fractions of total rated capacity
        profile = np.clip(total_wind_kw / max_rated_kw, 0.0, 1.0)

        # Annualized capex per kW of rated capacity (real discount rate)
        r_real = _real_rate(proj.discount_rate_nominal, proj.inflation_rate)
        annual_total = wt.capex_per_unit * float(count) * _crf(r_real, wt.lifetime_years)
        ep_cost_per_kw = annual_total / max_rated_kw

        wt_source: solph.network.Node = solph.components.Source(
            label="wind_turbine",
            outputs={
                dc_bus: solph.Flow(
                    fix=profile,
                    nominal_capacity=solph.Investment(
                        ep_costs=ep_cost_per_kw,
                        maximum=max_rated_kw,
                    ),
                )
            },
        )
        log.debug(
            "Wind: %d x %s (rated %.2f kW each), ep_costs=%.4f $/kW/yr",
            count,
            wt.turbine_model,
            rated_kw,
            ep_cost_per_kw,
        )
        return [wt_source]
