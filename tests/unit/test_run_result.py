# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for samba.run_result.reader.RunResult convenience accessors."""

from __future__ import annotations

from pathlib import Path

from samba.run_result.reader import RunResult
from samba.scenario.models import Scenario

_SCENARIO_RAW = {
    "project": {"name": "reader-test", "discount_rate_nominal": 0.08},
    "location": {"latitude": 37.0, "longitude": -122.0, "timezone": "America/Los_Angeles"},
    "weather": {"source": "csv", "csv_path": "d.csv"},
    "load": {"source": "hourly_csv", "csv_path": "d.csv"},
    "components": {
        "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
        "grid": {"capacity_kw": 100.0},
    },
    "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.15}},
}


class TestRunResultScenario:
    """The lazy, typed ``RunResult.scenario`` property (audit L4)."""

    def test_returns_typed_scenario(self) -> None:
        rr = RunResult(run_dir=Path("."), scenario_raw=dict(_SCENARIO_RAW))
        scenario = rr.scenario
        assert isinstance(scenario, Scenario)
        assert scenario.project.name == "reader-test"

    def test_none_when_scenario_raw_missing(self) -> None:
        rr = RunResult(run_dir=Path("."), scenario_raw=None)
        assert rr.scenario is None

    def test_result_is_cached(self) -> None:
        rr = RunResult(run_dir=Path("."), scenario_raw=dict(_SCENARIO_RAW))
        assert rr.scenario is rr.scenario  # same object returned on repeat access
