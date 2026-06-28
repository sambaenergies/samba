# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Regression: the `samba run` CLI must resolve weather for thermal scenarios.

Previously the CLI called ``samba.run`` without ``scenario_dir``, so weather fell
back to a stub and degree-day thermal demand read as zero (while the Python API /
golden path computed it correctly). This test runs a degree-day heat-pump scenario
through the CLI handler and asserts real thermal demand is produced.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

_WEATHER = Path(__file__).resolve().parents[2] / "examples" / "content" / "weather_sf_2019.csv"

_SCENARIO = """
schema_version: "2.0"
project:
  name: "cli-thermal-resolution"
  year: 2019
  lifetime_years: 20
  discount_rate_nominal: 0.06
  inflation_rate: 0.02
location:
  latitude: 37.77
  longitude: -122.42
  timezone: "America/Los_Angeles"
weather:
  source: "csv"
  csv_path: "weather.csv"
load:
  source: "generic_annual_total"
  annual_kwh: 4000.0
  thermal:
    enabled: true
    source: "degree_day"
    building_ua_kw_per_k: 0.5
    heating_setpoint_c: 20.0
    cooling_setpoint_c: 26.0
components:
  inverter: { capacity_kw: null, capex_per_kw: 314.0, efficiency: 0.96 }
  grid: { enabled: true, capacity_kw: 30.0 }
  heat_pump:
    enabled: true
    mode: "heating_only"
    sizing: "catalog_auto"
    cop_source: "catalog"
    capex: 4000.0
    lifetime_years: 15
tariff:
  buy: { type: "flat", rate_per_kwh: 0.15 }
constraints: { thermal_lpsp_max: 0.0 }
objective: { type: "cost" }
"""


@pytest.mark.integration
def test_cli_run_resolves_degree_day_thermal(tmp_path: Path) -> None:
    from samba_cli.handlers import run_command

    (tmp_path / "weather.csv").write_text(_WEATHER.read_text(encoding="utf-8"), encoding="utf-8")
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(_SCENARIO, encoding="utf-8")
    out_dir = tmp_path / "out"

    run_command(scenario_path, out_dir, solver="appsi_highs", time_limit=120, verbose=False)

    kpi_files = glob.glob(str(out_dir / "*" / "kpis.json"))
    assert kpi_files, "CLI run produced no kpis.json"
    kpis = json.loads(Path(kpi_files[0]).read_text(encoding="utf-8"))

    # The bug made these zero (weather stubbed); SF degree-day heating is substantial.
    demand = kpis.get("annual_heating_demand_kwh_th", 0.0)
    assert demand > 1000.0, f"degree-day heating demand not resolved via CLI: {demand}"
    assert kpis.get("annual_heat_produced_kwh", 0.0) > 1000.0
    assert kpis.get("mean_cop_heating", 0.0) > 1.0
