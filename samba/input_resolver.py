# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Resolve raw NumPy arrays from a validated scenario configuration.

This module contains the core data-pipeline step that converts a
``samba.scenario.models.Scenario`` into the array arguments required by
``samba.run``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from samba.scenario.models import Scenario
    from samba.weather.models import WeatherData

__all__ = ["resolve_arrays"]

# NSRDB weather CSVs provide wind speed measured at 10 m above ground.
_NSRDB_WIND_REF_HEIGHT_M = 10.0

# Hellmann exponent for open terrain (standard atmospheric stability class)
_WIND_SHEAR_EXPONENT = 0.14


def _adjust_wind_to_hub_height(
    wind_ms: np.ndarray,
    hub_height_m: float,
    ref_height_m: float = _NSRDB_WIND_REF_HEIGHT_M,
) -> np.ndarray:
    """Scale wind speed from reference height to turbine hub height."""
    if abs(hub_height_m - ref_height_m) < 0.1:
        return np.asarray(wind_ms, dtype=np.float64).copy()
    factor = (hub_height_m / ref_height_m) ** _WIND_SHEAR_EXPONENT
    return np.asarray(wind_ms * factor, dtype=np.float64)


def _resolve_weather(scenario: Scenario, base_dir: Path) -> WeatherData:
    """Load weather data from the scenario weather source."""
    from samba.weather import read_nsrdb_csv

    weather_cfg = scenario.weather

    if weather_cfg.source == "nsrdb":
        from samba.weather.fetch import fetch_weather

        loc = scenario.location
        return fetch_weather(
            latitude=loc.latitude,
            longitude=loc.longitude,
            year=scenario.project.year,
            source="nsrdb",
            api_key=weather_cfg.nsrdb_api_key,
            email=weather_cfg.nsrdb_email,
        )

    if weather_cfg.csv_path is None:
        raise ValueError("weather.csv_path is required when weather.source='csv'.")
    csv_p = Path(weather_cfg.csv_path)
    if not csv_p.is_absolute():
        csv_p = base_dir / csv_p

    return read_nsrdb_csv(csv_p)


def _resolve_load_kw(scenario: Scenario, base_dir: Path) -> np.ndarray:
    """Expand the scenario load configuration to an 8 760-element kW array."""
    from samba.load_profiles import expand_load

    return expand_load(scenario.load, base_dir=base_dir, peak_month=scenario.load.peak_month)


def _resolve_pv_per_kwp(
    scenario: Scenario,
    weather: WeatherData,
) -> np.ndarray | None:
    """Compute normalized PV output fraction per kWp from scenario + weather."""
    from samba.weather import calc_cell_temp, calc_poa, calc_pv_power_per_kwp

    pv = scenario.components.pv
    if pv is None or not pv.enabled:
        return None

    poa = calc_poa(
        weather,
        tilt_deg=pv.tilt_deg,
        azimuth_deg=pv.azimuth_deg,
        module_type=pv.module_type,
        bifaciality=pv.bifaciality,
    )
    t_cell = calc_cell_temp(poa, weather.tamb_c, noct_celsius=pv.noct_celsius)
    return calc_pv_power_per_kwp(
        poa,
        t_cell,
        temp_coeff=pv.temp_coeff_pmax,
        derating=pv.derating_factor,
    )


def _resolve_wind_power_kw(
    scenario: Scenario,
    weather: WeatherData,
) -> np.ndarray | None:
    """Compute per-turbine hourly wind power from scenario + weather."""
    from samba.compiler.builders import calc_wind_power_kw

    wt = scenario.components.wind_turbine
    if wt is None or not wt.enabled:
        return None

    wind_hub = _adjust_wind_to_hub_height(weather.wind_ms, hub_height_m=wt.hub_height_m)
    try:
        return calc_wind_power_kw(wind_hub, turbine_model=wt.turbine_model)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc


def resolve_arrays(
    scenario: Scenario,
    base_dir: Path,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
    """Resolve scenario configuration into raw NumPy arrays for ``samba.run``."""
    load_kw = _resolve_load_kw(scenario, base_dir)

    needs_weather = (scenario.components.pv is not None and scenario.components.pv.enabled) or (
        scenario.components.wind_turbine is not None and scenario.components.wind_turbine.enabled
    )

    weather: WeatherData | None = None
    if needs_weather:
        weather = _resolve_weather(scenario, base_dir)

    pv_per_kwp: np.ndarray | None = None
    wind_power_kw: np.ndarray | None = None

    if weather is not None:
        pv_per_kwp = _resolve_pv_per_kwp(scenario, weather)
        wind_power_kw = _resolve_wind_power_kw(scenario, weather)

    return load_kw, pv_per_kwp, wind_power_kw
