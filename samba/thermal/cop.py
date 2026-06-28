# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Coefficient-of-performance (COP) arrays for air-source heat pumps.

COP is derived from first principles as a fixed fraction of the reversible
(Carnot) limit, evaluated hourly against the outdoor dry-bulb temperature.
No manufacturer regression tables are used; see
:mod:`samba.thermal.constants` for the model parameters and references.

Heating
    ``COP_h = f_h * T_supply / (T_supply - T_outdoor)``  (absolute temps)
    -- larger when the outdoor air is warm (small lift).

Cooling
    ``COP_c = f_c * T_indoor_wb / (T_outdoor - T_indoor_wb)``  (absolute temps)
    -- larger when the outdoor air is cool (small lift). The cold-side
    reference is the indoor *wet-bulb* temperature, since the evaporator coil
    dehumidifies toward it; the wet-bulb is obtained from the Stull (2011)
    approximation.

Both arrays are clipped to ``[COP_FLOOR, COP_CEILING]``. The optimiser consumes
them as time-varying ``Converter.conversion_factors``; the relation
``thermal_output[t] = COP[t] * elec_input[t]`` stays linear.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from samba.thermal.constants import (
    CARNOT_FRACTION_COOLING,
    CARNOT_FRACTION_HEATING,
    CATALOG_MODEL_NAMES,
    COP_CEILING,
    COP_FLOOR,
    HEATING_SUPPLY_TEMP_C,
    KELVIN_OFFSET,
    MIN_TEMP_LIFT_K,
)
from samba.thermal.hp_catalog import (
    get_cooling_capacity_kw,
    get_heating_capacity_kw,
    select_catalog_model,
)

if TYPE_CHECKING:
    from samba.scenario.models import HeatPump

log = logging.getLogger(__name__)

__all__ = ["COPArrays", "compute_heating_cop", "compute_cooling_cop", "build_cop_arrays"]


@dataclass
class COPArrays:
    """Pre-computed hourly COP arrays for an HP at a given site.

    Attributes
    ----------
    heating:
        ``(8760,)`` array of heating COP values, or ``None`` when
        ``mode='cooling_only'``.
    cooling:
        ``(8760,)`` array of cooling COP values, or ``None`` when
        ``mode='heating_only'``.
    model_btu:
        Catalog rating in BTU/hr of the selected / configured model.
    model_name:
        Human-readable catalog model identifier (e.g. ``"ASHP-3ton"``).
    heating_capacity_kw:
        Rated heating output capacity in kW.
    cooling_capacity_kw:
        Rated cooling output capacity in kW.
    """

    heating: np.ndarray | None
    cooling: np.ndarray | None
    model_btu: int
    model_name: str
    heating_capacity_kw: float
    cooling_capacity_kw: float


# ---------------------------------------------------------------------------
# Psychrometric helpers
# ---------------------------------------------------------------------------


def _saturation_pressure_kpa(t_celsius: float) -> float:
    """Saturation water-vapour pressure [kPa] via the Tetens (1930) formula.

    ``p_ws = 0.61078 * exp(17.27 * T / (T + 237.3))``  (T in deg C).
    """
    return 0.61078 * float(np.exp(17.27 * t_celsius / (t_celsius + 237.3)))


def _relative_humidity_pct(
    t_celsius: float,
    humidity_ratio: float,
    pressure_kpa: float,
) -> float:
    """Relative humidity [%] from a humidity ratio via the ASHRAE relation.

    The vapour partial pressure follows from the humidity ratio
    ``w = 0.621945 * p_w / (p - p_w)`` solved for ``p_w``; relative humidity is
    then ``p_w / p_ws`` at the dry-bulb temperature.
    """
    p_w = humidity_ratio * pressure_kpa / (0.621945 + humidity_ratio)
    p_ws = _saturation_pressure_kpa(t_celsius)
    return 100.0 * p_w / p_ws


def _indoor_wet_bulb(
    t_indoor: float,
    humidity_ratio: float,
    pressure_kpa: float,
) -> float:
    """Indoor wet-bulb temperature [deg C] from the Stull (2011) approximation.

    Stull, R. (2011), "Wet-Bulb Temperature from Relative Humidity and Air
    Temperature", *J. Appl. Meteor. Climatol.* 50(11), 2267-2269. Valid for
    relative humidity 5-99 % and dry-bulb -20 to 50 deg C, which comfortably
    covers indoor design conditions. Because the indoor state is a fixed design
    constant (not time-varying), this returns a single scalar.

    Parameters
    ----------
    t_indoor:
        Indoor dry-bulb design temperature [deg C].
    humidity_ratio:
        Indoor design humidity ratio [kg/kg dry air].
    pressure_kpa:
        Atmospheric pressure [kPa].

    Returns
    -------
    float
        Indoor wet-bulb temperature [deg C].
    """
    rh = _relative_humidity_pct(t_indoor, humidity_ratio, pressure_kpa)
    t = t_indoor
    t_wb = (
        t * np.arctan(0.151977 * np.sqrt(rh + 8.313659))
        + np.arctan(t + rh)
        - np.arctan(rh - 1.676331)
        + 0.00391838 * rh**1.5 * np.arctan(0.023101 * rh)
        - 4.686035
    )
    return float(t_wb)


# ---------------------------------------------------------------------------
# COP array computations
# ---------------------------------------------------------------------------


def compute_heating_cop(
    t_outdoor: np.ndarray,
    supply_temp_c: float = HEATING_SUPPLY_TEMP_C,
    carnot_fraction: float = CARNOT_FRACTION_HEATING,
) -> np.ndarray:
    """Hourly heating COP from the Carnot limit times a practical fraction.

    The outdoor dry-bulb air is the cold reservoir; ``supply_temp_c`` is the
    hot (condenser) reservoir. COP is independent of the unit's nominal size --
    it is an intensive thermodynamic property.

    Parameters
    ----------
    t_outdoor:
        Hourly outdoor dry-bulb temperature [deg C], shape ``(8760,)``.
    supply_temp_c:
        Heating supply (condenser) temperature [deg C].
    carnot_fraction:
        Practical second-law efficiency (fraction of the Carnot COP achieved).

    Returns
    -------
    np.ndarray
        Shape matching ``t_outdoor``, values in ``[COP_FLOOR, COP_CEILING]``.
    """
    t_hot_k = supply_temp_c + KELVIN_OFFSET
    t_cold_k = np.asarray(t_outdoor, dtype=float) + KELVIN_OFFSET
    lift_k = np.maximum(t_hot_k - t_cold_k, MIN_TEMP_LIFT_K)
    cop = carnot_fraction * t_hot_k / lift_k
    cop = np.clip(cop, COP_FLOOR, COP_CEILING)
    log.debug(
        "Heating COP: mean=%.2f, range=[%.2f, %.2f]",
        float(np.mean(cop)),
        float(np.min(cop)),
        float(np.max(cop)),
    )
    return cop.astype(float)


def compute_cooling_cop(
    t_outdoor: np.ndarray,
    t_indoor: float = 22.22,
    humidity_ratio: float = 0.005,
    pressure_kpa: float = 101.325,
    carnot_fraction: float = CARNOT_FRACTION_COOLING,
) -> np.ndarray:
    """Hourly cooling COP from the Carnot limit times a practical fraction.

    The indoor wet-bulb (Stull 2011) is the cold reservoir; the outdoor
    dry-bulb air is the hot reservoir. Indoor conditions are fixed design
    constants, so the cold-side temperature is a pre-computed scalar.

    Parameters
    ----------
    t_outdoor:
        Hourly outdoor dry-bulb temperature [deg C], shape ``(8760,)``.
    t_indoor:
        Indoor design dry-bulb temperature [deg C].
    humidity_ratio:
        Indoor design humidity ratio [kg/kg dry air].
    pressure_kpa:
        Atmospheric pressure [kPa].
    carnot_fraction:
        Practical second-law efficiency (fraction of the Carnot COP achieved).

    Returns
    -------
    np.ndarray
        Shape matching ``t_outdoor``, values in ``[COP_FLOOR, COP_CEILING]``.
    """
    t_wb = _indoor_wet_bulb(t_indoor, humidity_ratio, pressure_kpa)
    t_cold_k = t_wb + KELVIN_OFFSET
    t_hot_k = np.asarray(t_outdoor, dtype=float) + KELVIN_OFFSET
    lift_k = np.maximum(t_hot_k - t_cold_k, MIN_TEMP_LIFT_K)
    cop = carnot_fraction * t_cold_k / lift_k
    cop = np.clip(cop, COP_FLOOR, COP_CEILING)
    log.debug(
        "Cooling COP: mean=%.2f, T_iwb=%.2f deg C, range=[%.2f, %.2f]",
        float(np.mean(cop)),
        t_wb,
        float(np.min(cop)),
        float(np.max(cop)),
    )
    return cop.astype(float)


# ---------------------------------------------------------------------------
# High-level builder
# ---------------------------------------------------------------------------


def build_cop_arrays(
    hp: HeatPump,
    t_outdoor: np.ndarray,
    peak_heating_kw: float = 0.0,
    peak_cooling_kw: float = 0.0,
    base_dir: Path | None = None,
) -> COPArrays:
    """Build :class:`COPArrays` for *hp* including catalog model selection.

    Parameters
    ----------
    hp:
        Validated :class:`~samba.scenario.models.HeatPump` config.
    t_outdoor:
        Hourly outdoor dry-bulb temperature [deg C], shape ``(8760,)``.
    peak_heating_kw:
        Peak heating demand [kW], used for catalog auto-selection.
    peak_cooling_kw:
        Peak cooling demand [kW], used for catalog auto-selection.
    base_dir:
        Directory used to resolve a relative ``hp.cop_dataset_path`` (typically
        the scenario YAML's directory). Only used when ``cop_source='dataset'``.

    Returns
    -------
    COPArrays
    """

    # ------- Resolve catalog model BTU rating --------
    if hp.sizing == "catalog_auto":
        peak_kw = max(peak_heating_kw, peak_cooling_kw)
        model_btu = select_catalog_model(peak_kw)
    else:
        # sizing == "fixed" -- infer BTU from capacity for the record lookup
        # Use peak of specified capacities; fall back to smallest if not set.
        peak_kw = max(
            hp.heating_capacity_kw or 0.0,
            hp.cooling_capacity_kw or 0.0,
        )
        if peak_kw > 0.0:
            from samba.thermal.constants import CATALOG_SIZES_BTU

            try:
                model_btu = select_catalog_model(peak_kw)
            except ValueError:
                # Demand exceeds catalog -- use largest model for the label.
                model_btu = CATALOG_SIZES_BTU[-1]
        else:
            from samba.thermal.constants import CATALOG_SIZES_BTU

            model_btu = CATALOG_SIZES_BTU[0]

    model_name = CATALOG_MODEL_NAMES.get(model_btu, str(model_btu))

    # ------- Capacity (kW) --------
    if hp.sizing == "fixed":
        h_cap_kw = hp.heating_capacity_kw or get_heating_capacity_kw(model_btu)
        c_cap_kw = hp.cooling_capacity_kw or get_cooling_capacity_kw(model_btu)
    else:
        h_cap_kw = get_heating_capacity_kw(model_btu)
        c_cap_kw = get_cooling_capacity_kw(model_btu)

    # ------- COP arrays --------
    mode = hp.mode

    cop_h: np.ndarray | None = None
    cop_c: np.ndarray | None = None
    need_h = mode in ("heating_only", "both")
    need_c = mode in ("cooling_only", "both")

    if hp.cop_source == "fixed":
        if need_h and hp.fixed_cop_heating is not None:
            cop_h = np.full(len(t_outdoor), hp.fixed_cop_heating, dtype=float)
        if need_c and hp.fixed_cop_cooling is not None:
            cop_c = np.full(len(t_outdoor), hp.fixed_cop_cooling, dtype=float)
    elif hp.cop_source == "dataset":
        # Empirical curves fitted from a user-supplied performance dataset.
        from samba.thermal.cop_dataset import evaluate_curve, fit_cop_curves

        if hp.cop_dataset_path is None:
            raise ValueError("cop_source='dataset' requires heat_pump.cop_dataset_path to be set")
        ds_path = Path(hp.cop_dataset_path)
        if not ds_path.is_absolute() and base_dir is not None:
            ds_path = Path(base_dir) / ds_path
        curves = fit_cop_curves(ds_path)
        if need_h:
            if curves.heating is None:
                raise ValueError(
                    f"cop_source='dataset' with mode={mode!r} needs heating points "
                    f"(a 'cop_heating' column) in {ds_path}"
                )
            cop_h = evaluate_curve(curves.heating, t_outdoor)
        if need_c:
            if curves.cooling is None:
                raise ValueError(
                    f"cop_source='dataset' with mode={mode!r} needs cooling points "
                    f"(a 'cop_cooling' column) in {ds_path}"
                )
            cop_c = evaluate_curve(curves.cooling, t_outdoor)
    else:
        # catalog -> physics-based (Carnot-fraction) COP curves
        cop_h = compute_heating_cop(t_outdoor) if need_h else None
        cop_c = (
            compute_cooling_cop(
                t_outdoor,
                t_indoor=hp.indoor_design_temp_c,
                humidity_ratio=hp.indoor_humidity_ratio,
                pressure_kpa=hp.atmospheric_pressure_kpa,
            )
            if need_c
            else None
        )

    log.info(
        "Heat pump: model %s (%d BTU/hr), mode=%s, "
        "h_cap=%.1f kW, c_cap=%.1f kW, "
        "mean_COP_h=%.2f, mean_COP_c=%.2f",
        model_name,
        model_btu,
        mode,
        h_cap_kw,
        c_cap_kw,
        float(np.mean(cop_h)) if cop_h is not None else 0.0,
        float(np.mean(cop_c)) if cop_c is not None else 0.0,
    )

    return COPArrays(
        heating=cop_h,
        cooling=cop_c,
        model_btu=model_btu,
        model_name=model_name,
        heating_capacity_kw=h_cap_kw,
        cooling_capacity_kw=c_cap_kw,
    )
