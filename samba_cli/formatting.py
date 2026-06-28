# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""samba_cli.formatting - Rich terminal output helpers for SAMBA CLI."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from samba.run_result.reader import RunResult

__all__ = [
    "console",
    "format_currency",
    "print_error",
    "print_success",
    "print_validation_errors",
]

console = Console(stderr=False)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_currency(value: float, symbol: str = "$") -> str:
    """Return a human-readable monetary string.

    Parameters
    ----------
    value:
        Numeric monetary value.
    symbol:
        Currency symbol prefix (e.g. ''"$"'', ''"EUR"'').

    Returns
    -------
    str
        E.g. ''"$125,432"'' or ''"EUR1,200,000"''.
    """
    if math.isnan(value) or math.isinf(value):
        return f"{symbol}?"
    return f"{symbol}{value:,.0f}"


# ---------------------------------------------------------------------------
# Panel printers
# ---------------------------------------------------------------------------


def print_error(title: str, detail: str) -> None:
    """Print a red error panel to the console.

    Parameters
    ----------
    title:
        Short error heading shown in the panel border.
    detail:
        Detailed error description shown in the panel body.
    """
    panel = Panel(
        f"[bold]{detail}[/bold]",
        title=f"[red]{title}[/red]",
        border_style="red",
        expand=False,
    )
    console.print(panel)


def print_success(result: RunResult, run_dir: Path, currency: str = "USD") -> None:
    """Print a green results summary table to the console.

    Parameters
    ----------
    result:
        :class:'~samba.run_result.reader.RunResult' returned by :func:'samba.run'.
    run_dir:
        The run output directory path to display.
    currency:
        Currency symbol or code from ''scenario.project.currency''.
        Three-letter codes are shown verbatim (e.g. ''"EUR"'');
        ''"USD"'' is rendered as ''"$"''.
    """
    symbol = "$" if currency in ("USD", "$") else currency + " "

    # KPI values
    npc = result.kpis.get("npc", float("nan"))
    lcoe = result.kpis.get("lcoe", float("nan"))
    rf = result.kpis.get("renewable_fraction", float("nan"))
    lpsp = result.kpis.get("lpsp", float("nan"))

    # Sizing values -- read from sizing DataFrame if available
    pv_kw: float = 0.0
    battery_kwh: float = 0.0
    if not result.sizing.empty:
        pv_row = result.sizing[result.sizing["component"] == "pv"]
        if not pv_row.empty:
            pv_kw = float(pv_row["capacity"].iloc[0])
        bat_row = result.sizing[result.sizing["component"] == "battery_energy"]
        if not bat_row.empty:
            battery_kwh = float(bat_row["capacity"].iloc[0])

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold cyan")
    table.add_column("Value", justify="right")

    table.add_row("NPC", format_currency(npc, symbol))
    table.add_row(
        "LCOE",
        f"{symbol}{lcoe:.4f}/kWh" if not (math.isnan(lcoe) or math.isinf(lcoe)) else "?",
    )
    if pv_kw > 0:
        table.add_row("PV size", f"{pv_kw:,.1f} kW")
    if battery_kwh > 0:
        table.add_row("Battery size", f"{battery_kwh:,.1f} kWh")
    if not math.isnan(rf):
        table.add_row("Renewable fraction", f"{rf * 100:.1f}%")
    if not math.isnan(lpsp):
        table.add_row("LPSP", f"{lpsp * 100:.2f}%")
    table.add_row("Run directory", str(run_dir))

    panel = Panel(
        table,
        title="[green]SAMBA Results[/green]",
        border_style="green",
        expand=False,
    )
    console.print(panel)


def print_validation_errors(errors: list[str]) -> None:
    """Print formatted validation error messages to the console.

    Parameters
    ----------
    errors:
        List of error strings, each typically formatted as
        ''"field.path: message"''.
    """
    lines = "\n".join(f"  [red]*[/red] {e}" for e in errors)
    panel = Panel(
        lines,
        title="[red]Validation Errors[/red]",
        border_style="red",
        expand=False,
    )
    console.print(panel)
