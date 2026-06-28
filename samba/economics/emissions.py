# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Greenhouse-gas emission estimates for diesel generators and grid imports.

Default emission factors:

* **Diesel**: 2.63 kg CO2-eq per litre (EPA AP-42 / IPCC tier-1 average).
* **Grid**: 0.0 kg CO2-eq per kWh (no grid emission factor supplied in v1 of
  the scenario schema; users can override via ''grid_emission_factor'').
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "dg_fuel_liters",
    "dg_emissions_kg",
    "grid_emissions_kg",
    "calc_diesel_co2_var_cost",
    "calc_grid_co2_var_cost",
]

#: Default diesel CO2-equivalent emission factor (kg per litre).
DEFAULT_DG_EMISSION_FACTOR: float = 2.63

#: Default grid CO2 factor (kg per kWh).  Zero until grid emission data is
#: included in the scenario schema.
DEFAULT_GRID_EMISSION_FACTOR: float = 0.0


def dg_fuel_liters(
    dg_gen_kwh: np.ndarray,
    capacity_kw: float,
    slope_l_per_kwh: float,
    intercept_l_per_kw_hr: float,
) -> float:
    """Estimate annual diesel fuel consumption in litres.

    Uses the standard *input-output* DG fuel curve:

    .. math::

       F = \\alpha \\cdot E_{DG} + \\beta \\cdot P_{rated} \\cdot H_{run}

    where

    * :math:'\\alpha' = ''slope_l_per_kwh'' (variable fuel slope, L/kWh),
    * :math:'\\beta' = ''intercept_l_per_kw_hr'' (no-load intercept, L/kW*hr),
    * :math:'E_{DG}' = total energy generated (kWh) = ''dg_gen_kwh.sum()'',
    * :math:'P_{rated}' = ''capacity_kw'',
    * :math:'H_{run}' = number of hours with DG output > 0.01 kW.

    Parameters
    ----------
    dg_gen_kwh:
        Time-series of DG electrical output (kWh per time-step, shape ''(T,)'').
        Typically 8 760 hourly steps for one simulated year.
    capacity_kw:
        Rated DG capacity in kW (used for the no-load term).
    slope_l_per_kwh:
        Variable fuel consumption slope [L / kWh].
    intercept_l_per_kw_hr:
        No-load fuel consumption intercept [L / (kW * hr)].

    Returns
    -------
    float
        Total fuel consumed in litres over the simulation period.

    Notes
    -----
    Operating hours are counted on the assumption that the DG is running
    whenever its output exceeds 0.01 kW (avoids counting numerical noise in
    the LP solver output).
    """
    e_total = float(np.sum(dg_gen_kwh))
    operating_hours = int(np.count_nonzero(dg_gen_kwh > 0.01))
    return slope_l_per_kwh * e_total + intercept_l_per_kw_hr * capacity_kw * operating_hours


def dg_emissions_kg(
    fuel_liters: float,
    factor: float = DEFAULT_DG_EMISSION_FACTOR,
) -> float:
    """Convert diesel fuel volume to CO2-equivalent emissions.

    Parameters
    ----------
    fuel_liters:
        Fuel consumed in litres.
    factor:
        Emission factor in kg CO2-eq per litre (default: ''2.63'').

    Returns
    -------
    float
        Total CO2-equivalent emissions in kilograms.
    """
    return fuel_liters * factor


def grid_emissions_kg(
    grid_bought_kwh: float,
    factor_kg_per_kwh: float = DEFAULT_GRID_EMISSION_FACTOR,
) -> float:
    """Estimate CO2-equivalent emissions from grid electricity imports.

    Parameters
    ----------
    grid_bought_kwh:
        Total grid electricity purchased in kWh over the year.
    factor_kg_per_kwh:
        Grid emission factor in kg CO2-eq per kWh (default: ''0.0'').

    Returns
    -------
    float
        CO2-equivalent emissions from grid purchases in kilograms.
    """
    return grid_bought_kwh * factor_kg_per_kwh


def calc_diesel_co2_var_cost(
    co2_per_liter_kg: float,
    slope_l_per_kwh: float,
    alpha: float,
) -> float:
    """Return the CO2 variable cost to add to the diesel ''fuel_source'' flow [$/kWh_e].

    This is the **slope** component only (no-load intercept is post-processed):

    .. math::

       c_{CO_2}^{DG} = \\text{co2\\_per\\_liter\\_kg} \\cdot
                       \\text{slope\\_l\\_per\\_kwh} \\cdot \\alpha

    Parameters
    ----------
    co2_per_liter_kg:
        Diesel CO2 emission factor [kg per litre].
    slope_l_per_kwh:
        DG fuel-curve slope [L/kWh_e].
    alpha:
        Carbon price [$/kg CO2].  Pass ''0.0'' for cost-only mode.

    Returns
    -------
    float
        Additional variable cost [$/kWh_e] to be summed with the fuel cost.
    """
    return co2_per_liter_kg * slope_l_per_kwh * alpha


def calc_grid_co2_var_cost(
    emission_factor_kg_per_kwh: float,
    alpha: float,
) -> float:
    """Return the CO2 variable cost to add to the grid import flow [$/kWh].

    .. math::

       c_{CO_2}^{grid} = \\text{emission\\_factor\\_kg\\_per\\_kwh} \\cdot \\alpha

    Parameters
    ----------
    emission_factor_kg_per_kwh:
        Grid CO2 intensity [kg per kWh imported].
    alpha:
        Carbon price [$/kg CO2].  Pass ''0.0'' for cost-only mode.

    Returns
    -------
    float
        Additional variable cost [$/kWh] to add to the buy-rate array.
    """
    return emission_factor_kg_per_kwh * alpha
