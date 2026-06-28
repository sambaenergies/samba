# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Shared command handlers for the SAMBA CLI."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from samba_cli.formatting import (
    console,
    print_error,
    print_success,
    print_validation_errors,
)

if TYPE_CHECKING:
    from samba.scenario.models import Scenario


def _raise_cli_error(title: str, detail: str, *, exit_code: int) -> None:
    print_error(title, detail)
    raise typer.Exit(exit_code)


def _ensure_scenario_exists(scenario: Path) -> None:
    if scenario.exists():
        return
    _raise_cli_error(
        "File not found",
        f"Scenario file does not exist: {scenario}",
        exit_code=1,
    )


def _load_scenario_or_exit(scenario: Path, *, title: str) -> Scenario:
    from samba.scenario import ScenarioValidationError, load_scenario

    try:
        return load_scenario(scenario)
    except FileNotFoundError as exc:
        _raise_cli_error("File not found", str(exc), exit_code=1)
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, ScenarioValidationError):
            msgs = getattr(exc, "messages", [str(exc)])
            print_validation_errors(msgs)
            raise typer.Exit(1) from None
        _raise_cli_error(title, str(exc), exit_code=1)

    raise typer.Exit(1)  # pragma: no cover


def _resolve_arrays_or_exit(
    scene: Scenario,
    base_dir: Path,
) -> tuple[Any, Any, Any]:
    from samba.input_resolver import resolve_arrays

    try:
        return resolve_arrays(scene, base_dir)
    except FileNotFoundError as exc:
        _raise_cli_error("Data file not found", str(exc), exit_code=3)
    except ValueError as exc:
        _raise_cli_error("Data pipeline error", str(exc), exit_code=3)
    except Exception as exc:  # noqa: BLE001
        _raise_cli_error(
            "Data pipeline error",
            f"Unexpected error resolving arrays: {exc}",
            exit_code=3,
        )

    raise typer.Exit(3)  # pragma: no cover


def run_command(
    scenario: Path,
    output_dir: Path,
    solver: str,
    time_limit: int,
    verbose: bool,
) -> None:
    _ensure_scenario_exists(scenario)
    scene = _load_scenario_or_exit(scenario, title="Scenario validation error")
    load_kw, pv_per_kwp, wind_power_kw = _resolve_arrays_or_exit(scene, scenario.parent.resolve())

    from samba.solver.runner import (
        InfeasibleError,
        SolverConfig,
        SolverNotFoundError,
        SolverTimeLimitError,
    )

    config = SolverConfig(
        solver_name=solver,
        time_limit_s=time_limit,
        output_verbose=verbose,
    )

    console.print(
        Panel(
            f"Scenario: [bold]{scene.project.name}[/bold]\n"
            f"Solver:   {solver}  |  Time limit: {time_limit} s",
            title="[cyan]Running SAMBA[/cyan]",
            border_style="cyan",
            expand=False,
        )
    )

    import samba

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            progress.add_task("Optimising...", total=None)
            result = samba.run(
                scene,
                load_kw=load_kw,
                pv_per_kwp=pv_per_kwp,
                wind_power_kw=wind_power_kw,
                output_dir=output_dir,
                config=config,
                # Needed so weather (and thermal/HP CSV paths) resolve relative to
                # the scenario file; otherwise degree-day thermal demand falls back
                # to a stub and reads as zero.
                scenario_dir=scenario.parent.resolve(),
            )
    except FileNotFoundError as exc:
        _raise_cli_error("File not found", str(exc), exit_code=1)
    except SolverNotFoundError as exc:
        _raise_cli_error(
            "Solver not found",
            f"{exc}\n\nInstall HiGHS: pip install highspy\n"
            "Or CBC:  conda install -c conda-forge coincbc",
            exit_code=2,
        )
    except InfeasibleError as exc:
        _raise_cli_error(
            "Infeasible problem",
            f"{exc}\n\nHints: check budget constraints, component limits, and load data.",
            exit_code=2,
        )
    except SolverTimeLimitError as exc:
        _raise_cli_error(
            "Solver time limit exceeded",
            f"{exc}\n\nIncrease --time-limit or simplify the scenario.",
            exit_code=2,
        )
    except ValueError as exc:
        _raise_cli_error("Data pipeline error", str(exc), exit_code=3)
    except Exception as exc:  # noqa: BLE001
        console.print_exception()
        _raise_cli_error("Internal error", f"Unexpected exception: {exc}", exit_code=4)

    print_success(result, result.run_dir, currency=scene.project.currency)


def validate_command(scenario: Path) -> None:
    _load_scenario_or_exit(scenario, title="Validation error")
    console.print(f"[green](ok)[/green] Scenario is valid: [bold]{scenario}[/bold]")
    raise typer.Exit(0)


def info_command() -> None:
    from samba._version import __version__ as samba_version

    try:
        import oemof.solph as _solph

        solph_ver: str = getattr(_solph, "__version__", "unknown")
    except ImportError:
        solph_ver = "not installed"

    try:
        import pyomo.version as _pyomo_ver

        pyomo_ver: str = str(_pyomo_ver.version)
    except Exception:  # noqa: BLE001
        try:
            import pyomo

            pyomo_ver = getattr(pyomo, "__version__", "unknown")
        except ImportError:
            pyomo_ver = "not installed"

    highs_ok = False
    try:
        import highspy  # noqa: F401

        highs_ok = True
    except ImportError:
        pass
    highs_status = (
        "[green](ok) available (highspy)[/green]" if highs_ok else "[red](x) not found[/red]"
    )

    cbc_ok = shutil.which("cbc") is not None
    cbc_status = "[green](ok) available[/green]" if cbc_ok else "[yellow](x) not found[/yellow]"

    try:
        import samba as _samba

        samba_loc = str(Path(_samba.__file__).parent)
    except ImportError:
        samba_loc = "unknown"

    python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold cyan", min_width=22)
    table.add_column("Value")
    table.add_row("SAMBA version", samba_version)
    table.add_row("Python version", python_ver)
    table.add_row("oemof-solph version", solph_ver)
    table.add_row("Pyomo version", pyomo_ver)
    table.add_row("HiGHS (default solver)", highs_status)
    table.add_row("CBC solver", cbc_status)
    table.add_row("samba location", samba_loc)

    console.print(
        Panel(
            table,
            title="[cyan]SAMBA Environment[/cyan]",
            border_style="cyan",
            expand=False,
        )
    )


def serve_command(
    *,
    host: str,
    port: int,
    run_dir: Path,
    data_dir: Path | None,
    solver: str,
    time_limit: int,
    api_key: str | None,
    cors_origins: str | None,
    max_concurrent: int,
) -> None:
    try:
        import uvicorn
    except ImportError:
        _raise_cli_error(
            "Missing dependency",
            "uvicorn is required to start the service.\n"
            "Install it with: pip install samba-core[service]",
            exit_code=1,
        )

    try:
        from samba_service.config import config as svc_config
    except ImportError:
        _raise_cli_error(
            "Missing dependency",
            "samba_service is not installed.\nInstall it with: pip install samba-core[service]",
            exit_code=1,
        )

    svc_config.run_base_dir = run_dir
    svc_config.host = host
    svc_config.port = port
    svc_config.solver = solver
    svc_config.time_limit_s = time_limit
    svc_config.max_concurrent = max_concurrent
    if data_dir is not None:
        svc_config.data_dir = data_dir
    if api_key is not None:
        svc_config.api_key = api_key
    if cors_origins is not None:
        svc_config.cors_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]

    auth_status = (
        "[green]enabled[/green]" if svc_config.api_key else "[yellow]disabled (no key set)[/yellow]"
    )

    console.print(
        Panel(
            f"Host:         [bold]{host}:{port}[/bold]\n"
            f"Run dir:      {run_dir}\n"
            f"Data dir:     {svc_config.data_dir}\n"
            f"Solver:       {solver}  |  Time limit: {time_limit} s\n"
            f"Max jobs:     {max_concurrent}\n"
            f"Auth:         {auth_status}\n"
            f"CORS origins: {', '.join(svc_config.cors_origins)}\n\n"
            f"Docs:         [cyan]http://{host}:{port}/docs[/cyan]",
            title="[cyan]Starting SAMBA Service v2[/cyan]",
            border_style="cyan",
            expand=False,
        )
    )

    uvicorn.run("samba_service.app:app", host=host, port=port, reload=False)


def pareto_command(
    scenario: Path,
    n_points: int,
    output_dir: Path,
    solver: str,
    time_limit: int,
    verbose: bool,
    method: str = "weighted_sum",
) -> None:
    _ensure_scenario_exists(scenario)
    scene = _load_scenario_or_exit(scenario, title="Scenario validation error")
    load_kw, pv_per_kwp, wind_power_kw = _resolve_arrays_or_exit(scene, scenario.parent.resolve())

    from samba.pareto import default_alpha_range, run_pareto_sweep, run_pareto_sweep_epsilon
    from samba.pareto.sweep import write_pareto_results
    from samba.solver.runner import SolverConfig

    config = SolverConfig(
        solver_name=solver,
        time_limit_s=time_limit,
        output_verbose=verbose,
    )
    is_epsilon = method == "epsilon"
    alphas = default_alpha_range(n_points)
    method_desc = (
        "epsilon-constraint (captures non-convex regions)"
        if is_epsilon
        else "weighted-sum (convex hull only)"
    )

    console.print(
        Panel(
            f"Scenario:  [bold]{scene.project.name}[/bold]\n"
            f"Method:    {method_desc}\n"
            f"Sweep:     {n_points} points\n"
            f"Output:    {output_dir}\n"
            f"Solver:    {solver}  |  Time limit: {time_limit} s / point",
            title="[cyan]SAMBA Pareto Sweep[/cyan]",
            border_style="cyan",
            expand=False,
        )
    )

    points = []
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Sweep", total=n_points)

            def _cb(idx: int, total: int, value: float) -> None:
                label = "epsilon" if is_epsilon else "alpha"
                progress.update(
                    task,
                    completed=idx,
                    description=(f"Point {idx + 1}/{total}  {label}={value:.4g}"),
                )

            if is_epsilon:
                points = run_pareto_sweep_epsilon(
                    scene,
                    load_kw=load_kw,
                    n_points=n_points,
                    run_base_dir=output_dir,
                    pv_per_kwp=pv_per_kwp,
                    wind_power_kw=wind_power_kw,
                    config=config,
                    progress_callback=_cb,
                    scenario_dir=scenario.parent.resolve(),
                )
            else:
                points = run_pareto_sweep(
                    scene,
                    load_kw=load_kw,
                    alphas=alphas,
                    run_base_dir=output_dir,
                    pv_per_kwp=pv_per_kwp,
                    wind_power_kw=wind_power_kw,
                    config=config,
                    progress_callback=_cb,
                    scenario_dir=scenario.parent.resolve(),
                )
            progress.update(task, completed=n_points, description="Done")
    except KeyboardInterrupt:
        _raise_cli_error("Interrupted", "Pareto sweep cancelled by user", exit_code=1)
    except Exception as exc:  # noqa: BLE001
        console.print_exception()
        _raise_cli_error("Sweep error", f"Unexpected exception: {exc}", exit_code=4)

    if not points:
        _raise_cli_error(
            "No results",
            "All sweep points failed -- check solver / scenario settings",
            exit_code=2,
        )

    currency = scene.project.currency
    table = Table(
        title="[cyan]Pareto Front (cost vs emissions)[/cyan]",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("alpha [$/kg CO2]", justify="right")
    table.add_column(f"NPC [{currency}]", justify="right")
    table.add_column("LEM [kg/kWh]", justify="right")
    table.add_column("Emissions [t/yr]", justify="right")
    table.add_column("Non-dominated", justify="center")

    for point in points:
        is_non_dominated = "[green]yes[/green]" if not point.dominated else "[yellow]no[/yellow]"
        table.add_row(
            f"{point.alpha:.4g}",
            f"{point.npc:,.0f}",
            f"{point.lem:.4f}",
            f"{point.total_emissions_kg / 1000:.1f}",
            is_non_dominated,
        )

    console.print(table)

    write_pareto_results(points, output_dir)
    non_dominated_count = sum(1 for point in points if not point.dominated)
    console.print(
        f"\n[green]\u2713[/green] {len(points)} points computed "
        f"({non_dominated_count} non-dominated).\n"
        f"  Saved: {output_dir / 'pareto_front.csv'}\n"
        f"         {output_dir / 'pareto_front.json'}"
    )


def fetch_weather_command(
    latitude: float,
    longitude: float,
    year: int,
    api_key: str | None,
    email: str | None,
    cache_dir: Path | None,
) -> None:
    """Fetch a year of NSRDB weather for a site and cache it as an NSRDB-format CSV."""
    from samba.weather.fetch import WeatherFetchError, fetch_weather, nsrdb_cache_file

    target = nsrdb_cache_file(latitude, longitude, year, cache_dir)
    try:
        weather = fetch_weather(
            latitude=latitude,
            longitude=longitude,
            year=year,
            source="nsrdb",
            api_key=api_key,
            email=email,
            cache_dir=cache_dir,
        )
    except WeatherFetchError as exc:
        _raise_cli_error("Weather fetch error", str(exc), exit_code=2)

    console.print(
        Panel(
            f"Site:      [bold]{latitude:.4f}, {longitude:.4f}[/bold]  (year {year})\n"
            f"Rows:      {len(weather.timestamp)}\n"
            f"Cached at: {target}\n\n"
            f'Use it with:  weather: {{ source: csv, csv_path: "{target}" }}\n'
            f"or directly:  weather: {{ source: nsrdb }}  (auto-fetches + caches)",
            title="[green]SAMBA Weather Fetch[/green]",
            border_style="green",
            expand=False,
        )
    )


def fetch_cop_data_command(
    out_path: Path,
    from_file: Path | None,
    url: str | None,
    source_label: str,
) -> None:
    """Source a heat-pump COP dataset and write a curated CSV for cop_source=dataset."""
    from samba.thermal.cop_fetch import build_cop_dataset

    if (from_file is None) == (url is None):
        _raise_cli_error(
            "COP fetch error",
            "Provide exactly one of --from-file or --url.",
            exit_code=2,
        )
    try:
        written = build_cop_dataset(
            out_path=out_path,
            from_file=from_file,
            url=url,
            source_label=source_label,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        _raise_cli_error("COP fetch error", str(exc), exit_code=2)

    console.print(
        Panel(
            f"Source:    [bold]{source_label}[/bold]\n"
            f"Curated:   {written}\n\n"
            f'Use it with:  heat_pump: {{ cop_source: dataset, cop_dataset_path: "{written}" }}\n\n'
            "[yellow]LOCAL USE ONLY: this file is git-ignored by default. Do not "
            "commit or redistribute it unless the source grants those rights.[/yellow]",
            title="[green]SAMBA COP Data Fetch[/green]",
            border_style="green",
            expand=False,
        )
    )
