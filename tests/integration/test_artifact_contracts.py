# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Contract test: real solver artifacts must validate against the Pydantic models.

This guards the *backend* side of the schema-first pipeline: if ``compute_kpis`` /
``build_economics`` / the sizing table gain or rename a field without the
:mod:`samba.run_result.contracts` models being updated, this fails. (The schema
export drift test guards the other direction — model vs committed JSON Schema.)

Note: golden ``reference.json`` files carry a *curated KPI subset* for golden
comparison, not the full ``kpis.json`` artifact — so we validate against a real
run here rather than the goldens.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from samba.run_result.contracts import EconomicsReport, KpiSummary, SizingRow

_WEATHER = Path(__file__).resolve().parents[2] / "examples" / "content" / "weather_sf_2019.csv"

_SCENARIO = """
schema_version: "2.0"
project:
  name: "artifact-contracts"
  year: 2019
  lifetime_years: 20
  discount_rate_nominal: 0.07
  inflation_rate: 0.025
location:
  latitude: 37.77
  longitude: -122.42
  timezone: "America/Los_Angeles"
weather:
  source: "csv"
  csv_path: "weather.csv"
load:
  source: "generic_annual_total"
  annual_kwh: 6000.0
components:
  inverter: { capacity_kw: null, capex_per_kw: 300.0, efficiency: 0.97 }
  pv: { enabled: true, capacity_kw: null, capex_per_kw: 900.0 }
  grid: { enabled: true, capacity_kw: 30.0 }
tariff:
  buy: { type: "flat", rate_per_kwh: 0.20 }
objective: { type: "cost" }
"""


@pytest.mark.integration
def test_real_artifacts_match_contracts(tmp_path: Path) -> None:
    from samba_cli.handlers import run_command

    (tmp_path / "weather.csv").write_text(_WEATHER.read_text(encoding="utf-8"), encoding="utf-8")
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(_SCENARIO, encoding="utf-8")
    out_dir = tmp_path / "out"

    run_command(scenario_path, out_dir, solver="appsi_highs", time_limit=120, verbose=False)

    run_dirs = list(out_dir.glob("*/kpis.json"))
    assert run_dirs, "run produced no kpis.json"
    run_dir = run_dirs[0].parent

    # kpis.json — strict (extra="forbid"): catches added/renamed/dropped KPI fields.
    kpis = json.loads((run_dir / "kpis.json").read_text(encoding="utf-8"))
    KpiSummary.model_validate(kpis)

    # economics.json — top-level contract + cashflow_annual rows.
    economics = json.loads((run_dir / "economics.json").read_text(encoding="utf-8"))
    report = EconomicsReport.model_validate(economics)
    assert len(report.cashflow_annual) == economics["project_lifetime_years"] + 1

    # sizing.csv — one strict row per component.
    rows = list(csv.DictReader(io.StringIO((run_dir / "sizing.csv").read_text(encoding="utf-8"))))
    assert rows, "sizing.csv has no rows"
    for row in rows:
        SizingRow.model_validate(
            {
                "component": row["component"],
                "capacity": float(row["capacity"]),
                "unit": row["unit"],
                "count": int(row["count"]),
                "capital_cost": float(row["capital_cost"]),
            }
        )

    # dispatch.csv — wide/dynamic; sanity-check it has a timestamp index + columns.
    dispatch_header = (run_dir / "dispatch.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "timestamp" in dispatch_header.lower()
    assert dispatch_header.count(",") >= 1
