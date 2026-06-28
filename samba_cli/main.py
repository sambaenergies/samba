# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""samba_cli.main - Typer application for the SAMBA command-line interface."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from samba_cli.handlers import (
    fetch_cop_data_command,
    fetch_weather_command,
    info_command,
    pareto_command,
    run_command,
    serve_command,
    validate_command,
)


def _load_dotenv() -> None:
    """Load ``KEY=VALUE`` pairs from a local ``.env`` into the environment.

    Dependency-free and conservative: a real shell environment variable always
    wins (we never overwrite an existing value), unknown/blank/comment lines are
    skipped, and a missing/unreadable ``.env`` is a silent no-op. Lets users keep
    secrets like ``NREL_API_KEY`` in a git-ignored ``.env`` (see ``.env.example``).
    """
    env_path = Path.cwd() / ".env"
    if not env_path.is_file():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


_load_dotenv()

app = typer.Typer(
    name="samba",
    help="SAMBA -- Systems Advisor for Microgrids & Building Analysis",
    add_completion=True,
    rich_markup_mode="rich",
)


@app.command()
def run(
    scenario: Path = typer.Argument(..., help="Path to scenario YAML file"),  # noqa: B008
    output_dir: Path = typer.Option(  # noqa: B008
        Path("results"),
        "--output-dir",
        "-o",
        help="Base directory for run artifacts",
    ),
    solver: str = typer.Option("appsi_highs", "--solver", "-s", help="LP solver name"),  # noqa: B008
    time_limit: int = typer.Option(600, "--time-limit", help="Solver time limit in seconds"),  # noqa: B008
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show solver output"),  # noqa: B008
) -> None:
    """Run the full SAMBA optimisation pipeline on a scenario YAML file."""
    run_command(scenario, output_dir, solver, time_limit, verbose)


@app.command()
def validate(
    scenario: Path = typer.Argument(..., help="Path to scenario YAML file"),  # noqa: B008
) -> None:
    """Validate a scenario YAML file without running a solve."""
    validate_command(scenario)


@app.command()
def info() -> None:
    """Display environment and dependency information for SAMBA."""
    info_command()


@app.command(name="fetch-weather")
def fetch_weather(
    latitude: float = typer.Option(..., "--lat", help="Site latitude [deg]"),  # noqa: B008
    longitude: float = typer.Option(..., "--lon", help="Site longitude [deg]"),  # noqa: B008
    year: int = typer.Option(..., "--year", help="Calendar year to fetch"),  # noqa: B008
    api_key: str | None = typer.Option(  # noqa: B008
        None, "--api-key", help="NREL API key (or set NREL_API_KEY)"
    ),
    email: str | None = typer.Option(  # noqa: B008
        None, "--email", help="NREL API email (or set NREL_API_EMAIL)"
    ),
    cache_dir: Path | None = typer.Option(  # noqa: B008
        None, "--cache-dir", "-o", help="Directory to cache the NSRDB CSV (default: ~/.cache/samba)"
    ),
) -> None:
    """Fetch a year of NSRDB weather for a site and cache it as an NSRDB-format CSV."""
    fetch_weather_command(latitude, longitude, year, api_key, email, cache_dir)


@app.command(name="fetch-cop-data")
def fetch_cop_data(
    out_path: Path = typer.Option(  # noqa: B008
        Path("cop_dataset.csv"),
        "--out",
        "-o",
        help="Where to write the curated COP dataset CSV (git-ignore this).",
    ),
    from_file: Path | None = typer.Option(  # noqa: B008
        None, "--from-file", help="Normalise an already-downloaded raw export CSV."
    ),
    url: str | None = typer.Option(  # noqa: B008
        None, "--url", help="Download a raw export from this URL, then normalise it."
    ),
    source_label: str = typer.Option(  # noqa: B008
        "NEEP cold-climate ASHP list", "--source", help="Provenance label for the header."
    ),
) -> None:
    """Source a heat-pump COP dataset (e.g. NEEP) into SAMBA's cop_source=dataset schema.

    Provide exactly one of --from-file or --url. Confirm the source's license
    before committing the curated CSV; SAMBA ships no third-party HP data.
    """
    fetch_cop_data_command(out_path, from_file, url, source_label)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),  # noqa: B008
    port: int = typer.Option(8000, "--port", help="Bind port"),  # noqa: B008
    run_dir: Path = typer.Option(  # noqa: B008
        Path("results"),
        "--run-dir",
        help="Base directory for run artifacts",
    ),
    data_dir: Path = typer.Option(  # noqa: B008
        None,
        "--data-dir",
        help=(
            "Base directory for resolving relative CSV paths in scenarios. "
            "Defaults to the current working directory."
        ),
    ),
    solver: str = typer.Option("appsi_highs", "--solver", help="LP solver name"),  # noqa: B008
    time_limit: int = typer.Option(  # noqa: B008
        600, "--time-limit", help="Solver time limit in seconds"
    ),
    api_key: str = typer.Option(  # noqa: B008
        None,
        "--api-key",
        envvar="SAMBA_API_KEY",
        help=(
            "API key for X-API-Key authentication.  When set, all non-health "
            "endpoints require a matching X-API-Key header.  Also readable from "
            "the SAMBA_API_KEY environment variable."
        ),
    ),
    cors_origins: str = typer.Option(  # noqa: B008
        None,
        "--cors-origins",
        envvar="SAMBA_CORS_ORIGINS",
        help=(
            "Comma-separated list of allowed CORS origins (e.g. "
            "'http://localhost:3000,https://myapp.example.com').  "
            "Defaults to '*' (allow all).  Also readable from SAMBA_CORS_ORIGINS."
        ),
    ),
    max_concurrent: int = typer.Option(  # noqa: B008
        4,
        "--max-concurrent",
        help="Maximum number of simultaneous background solve jobs.",
    ),
) -> None:
    """Start the SAMBA REST service."""
    serve_command(
        host=host,
        port=port,
        run_dir=run_dir,
        data_dir=data_dir,
        solver=solver,
        time_limit=time_limit,
        api_key=api_key,
        cors_origins=cors_origins,
        max_concurrent=max_concurrent,
    )


@app.command()
def pareto(
    scenario: Path = typer.Argument(..., help="Path to scenario YAML file"),  # noqa: B008
    n_points: int = typer.Option(  # noqa: B008
        10,
        "--n-points",
        "-n",
        help="Number of sweep points (includes the alpha=0 cost-only reference)",
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        Path("pareto"),
        "--output-dir",
        "-o",
        help="Directory for per-point artifacts and pareto_front.csv / .json",
    ),
    solver: str = typer.Option("appsi_highs", "--solver", "-s", help="LP solver name"),  # noqa: B008
    time_limit: int = typer.Option(600, "--time-limit", help="Solver time limit per point (s)"),  # noqa: B008
    method: str = typer.Option(  # noqa: B008
        "weighted_sum",
        "--method",
        "-m",
        help="'weighted_sum' (fast, convex hull only) or 'epsilon' (captures non-convex regions)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show solver output"),  # noqa: B008
) -> None:
    """Generate a Pareto front of the cost vs emissions trade-off.

    Two methods are available via --method:

    - 'weighted_sum' (default): fast scalarisation that recovers only points on
      the CONVEX HULL of the true frontier; non-convex (concave) regions are
      omitted and points may cluster unevenly.
    - 'epsilon': the epsilon-constraint method, which caps emissions at a series
      of thresholds and minimises cost, capturing non-convex regions the
      weighted-sum method misses (slower; two extra endpoint solves).
    """
    pareto_command(scenario, n_points, output_dir, solver, time_limit, verbose, method)


if __name__ == "__main__":
    app()
