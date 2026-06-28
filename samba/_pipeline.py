# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Internal orchestration pipeline for :func:`samba.run`.

This module keeps the public package ``__init__`` lightweight while preserving
the same top-level ``samba.run(...)`` behavior.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd

    from samba.run_result.reader import RunResult
    from samba.scenario.models import Scenario
    from samba.solver.runner import SolverConfig
    from samba.tariff.resolver import TariffArrays
    from samba.weather import WeatherData

log = logging.getLogger(__name__)


def _load_scenario(
    scenario_or_path: Scenario | Path | str,
    scenario_dir: Path | str | None,
) -> tuple[Scenario, Path | None]:
    """Return validated scenario and resolved scenario directory."""
    from samba.scenario import Scenario, load_scenario

    resolved_dir: Path | None = Path(scenario_dir) if scenario_dir is not None else None
    if isinstance(scenario_or_path, Scenario):
        return scenario_or_path, resolved_dir

    scenario_path = Path(scenario_or_path)
    scenario = load_scenario(scenario_path)
    if resolved_dir is None:
        resolved_dir = scenario_path.parent
    return scenario, resolved_dir


def _resolve_tariff_arrays(
    scenario: Scenario,
    load_kw: np.ndarray,
    tariff_arrays: TariffArrays | None,
) -> TariffArrays:
    """Resolve tariff arrays from the scenario when not pre-provided."""
    from samba.tariff import resolve_tariff

    if tariff_arrays is None:
        return resolve_tariff(scenario.tariff, load_kw, scenario.project.year)
    return tariff_arrays


def _resolve_weather(
    scenario: Scenario,
    scenario_dir: Path | None,
    weather: WeatherData | None,
) -> WeatherData:
    """Resolve weather for thermal scenarios, with a safe fallback stub."""
    from samba.weather import stub_weather

    resolved_weather = weather
    if resolved_weather is None and scenario_dir is not None:
        hp = scenario.components.heat_pump
        thermal_cfg = getattr(getattr(scenario, "load", None), "thermal", None)
        needs_weather = (hp is not None and hp.enabled) or (
            thermal_cfg is not None
            and getattr(thermal_cfg, "enabled", False)
            and getattr(thermal_cfg, "source", None) == "degree_day"
        )
        if needs_weather and scenario.weather.source == "csv" and scenario.weather.csv_path:
            from samba.weather.nsrdb import read_nsrdb_csv

            weather_path = Path(scenario.weather.csv_path)
            if not weather_path.is_absolute():
                weather_path = scenario_dir / weather_path
            try:
                resolved_weather = read_nsrdb_csv(weather_path)
                log.debug("Auto-resolved weather from %s for HP/thermal scenario", weather_path)
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not auto-resolve weather for HP scenario: %s", exc)

    return resolved_weather if resolved_weather is not None else stub_weather()


def _compile_energy_system(
    scenario: Scenario,
    load_kw: np.ndarray,
    tariff_arrays: TariffArrays,
    weather: WeatherData,
    pv_per_kwp: np.ndarray | None,
    wind_power_kw: np.ndarray | None,
    scenario_dir: Path | None,
) -> object:
    """Compile the oemof energy system from run inputs."""
    from samba.compiler import CompilerInputs, compile_energy_system

    inputs = CompilerInputs(
        scenario=scenario,
        load_kw=load_kw,
        tariff_arrays=tariff_arrays,
        weather=weather,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        scenario_dir=scenario_dir,
    )
    return compile_energy_system(inputs)


def _solve_energy_system(
    energy_system: object,
    scenario: Scenario,
    config: SolverConfig | None,
) -> tuple[object, SolverConfig, float]:
    """Solve compiled system and return raw results + config + runtime."""
    from samba.solver.runner import SolverConfig, solve

    solver_config = config if config is not None else SolverConfig()
    t0 = time.perf_counter()
    raw_results = solve(energy_system, scenario, solver_config)
    solve_time_s = time.perf_counter() - t0
    log.info("Solve completed in %.2f s", solve_time_s)
    return raw_results, solver_config, solve_time_s


def _validate_kibam_if_needed(
    scenario: Scenario,
    dispatch_df: pd.DataFrame,
    config: SolverConfig,
) -> None:
    """Run post-solve KiBaM feasibility validation when enabled."""
    bat = scenario.components.battery
    if not (
        bat is not None
        and bat.enabled
        and bat.chemistry == "kibam"
        and bat.kibam is not None
        and config.kibam_validate
    ):
        return

    from samba.batteries.kibam import validate_kibam_dispatch
    from samba.compiler.constraints import ConstraintViolationError

    if "batt_discharge" not in dispatch_df or "batt_charge" not in dispatch_df:
        return

    batt_dch = dispatch_df["batt_discharge"].to_numpy()
    batt_ch = dispatch_df["batt_charge"].to_numpy()
    net_dispatch = batt_dch - batt_ch  # positive = discharge
    fixed_cap = bat.capacity_kwh if bat.capacity_kwh is not None else 0.0

    try:
        kibam_result = validate_kibam_dispatch(
            dispatch_kw=net_dispatch,
            capacity_kwh=float(dispatch_df["battery_soc_kwh"].max()) / bat.soc_max
            if "battery_soc_kwh" in dispatch_df
            else max(fixed_cap, 1.0),
            kibam=bat.kibam,
            soc_initial=bat.soc_initial,
        )
        if not kibam_result.feasible:
            log.warning(
                "KiBaM post-validation: %d timestep violation(s) detected. "
                "Worst Q1 deficit = %.4f kWh. "
                "LP approximation may have allowed infeasible discharge near low SOC.",
                kibam_result.n_violations,
                kibam_result.worst_q1_deficit_kwh,
            )
            if config.strict_kibam:
                raise ConstraintViolationError(
                    field="kibam_dispatch_feasibility",
                    value=float(kibam_result.n_violations),
                    limit=0.0,
                    deviation=float(kibam_result.n_violations),
                    message=(
                        f"KiBaM dispatch infeasible: {kibam_result.n_violations} timestep "
                        f"violation(s), worst Q1 deficit "
                        f"{kibam_result.worst_q1_deficit_kwh:.4f} kWh. The LP relaxation "
                        "allowed discharge the two-tank model cannot sustain near low SOC. "
                        "Set SolverConfig.strict_kibam=False to downgrade to a warning."
                    ),
                )
        else:
            log.debug("KiBaM post-validation: all timesteps feasible.")
    except ConstraintViolationError:
        raise  # strict_kibam: propagate, do not swallow below
    except Exception as exc:  # pragma: no cover
        log.debug("KiBaM post-validation skipped: %s", exc)


def _write_run_artifacts(
    output_dir: Path | str | None,
    scenario: Scenario,
    config: SolverConfig,
    solve_time_s: float,
    raw_results: Any,
    dispatch_df: pd.DataFrame,
    kpis: dict[str, Any],
    economics: dict[str, Any],
    sizing: pd.DataFrame,
    tariff_arrays: TariffArrays,
) -> tuple[Path | None, dict[str, Any]]:
    """Persist run artifacts when output directory is provided."""
    from samba.run_result.writer import (
        build_metadata,
        ensure_run_dir,
        write_dispatch,
        write_economics,
        write_kpis,
        write_metadata,
        write_scenario,
        write_sizing,
        write_tariff,
    )

    if output_dir is None:
        return (
            None,
            build_metadata(
                scenario=scenario,
                solver_config=config,
                solve_time_s=solve_time_s,
                solver_results=raw_results,
                run_id="in_memory",
            ),
        )

    run_dir = ensure_run_dir(Path(output_dir), scenario.project.name)
    write_dispatch(run_dir, dispatch_df)
    metadata = write_metadata(run_dir, scenario, config, solve_time_s, raw_results)
    write_kpis(run_dir, kpis)
    write_economics(run_dir, economics)
    write_sizing(run_dir, sizing)
    write_tariff(run_dir, tariff_arrays)
    write_scenario(run_dir, scenario)
    log.info("Results written to %s", run_dir)
    return run_dir, metadata


def run_pipeline(
    scenario_or_path: Scenario | Path | str,
    *,
    load_kw: np.ndarray,
    output_dir: Path | str | None = None,
    config: SolverConfig | None = None,
    pv_per_kwp: np.ndarray | None = None,
    tariff_arrays: TariffArrays | None = None,
    wind_power_kw: np.ndarray | None = None,
    weather: WeatherData | None = None,
    scenario_dir: Path | str | None = None,
) -> RunResult:
    """Execute full solve-and-postprocess pipeline and return ``RunResult``."""
    from samba.run_result.kpis import compute_kpis
    from samba.run_result.reader import RunResult
    from samba.solver.extract import extract_dispatch

    scenario, resolved_scenario_dir = _load_scenario(scenario_or_path, scenario_dir)
    resolved_tariff = _resolve_tariff_arrays(scenario, load_kw, tariff_arrays)
    resolved_weather = _resolve_weather(scenario, resolved_scenario_dir, weather)

    energy_system = _compile_energy_system(
        scenario,
        load_kw,
        resolved_tariff,
        resolved_weather,
        pv_per_kwp,
        wind_power_kw,
        resolved_scenario_dir,
    )

    raw_results, solver_config, solve_time_s = _solve_energy_system(energy_system, scenario, config)
    dispatch_result = extract_dispatch(energy_system, raw_results)

    _validate_kibam_if_needed(
        scenario=scenario,
        dispatch_df=dispatch_result.dispatch,
        config=solver_config,
    )

    kpis, economics, sizing = compute_kpis(scenario, dispatch_result, resolved_tariff)
    run_dir, metadata = _write_run_artifacts(
        output_dir=output_dir,
        scenario=scenario,
        config=solver_config,
        solve_time_s=solve_time_s,
        raw_results=raw_results,
        dispatch_df=dispatch_result.dispatch,
        kpis=kpis,
        economics=economics,
        sizing=sizing,
        tariff_arrays=resolved_tariff,
    )

    return RunResult(
        run_dir=run_dir or Path("."),
        metadata=metadata,
        kpis=kpis,
        dispatch=dispatch_result.dispatch,
        economics=economics,
        sizing=sizing,
        scenario_raw=None,
    )
