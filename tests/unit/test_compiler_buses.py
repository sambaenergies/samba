# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for samba.compiler.buses — BusSet dataclass and build_buses()."""

from __future__ import annotations

from typing import Any

import oemof.solph as solph

from samba.compiler.buses import BusSet, build_buses
from samba.scenario.models import Scenario
from samba.thermal.buses import ThermalBusSet

# ---------------------------------------------------------------------------
# Scenario factory helpers (matching test_compiler.py style)
# ---------------------------------------------------------------------------

_BASE_SCENARIO: dict[str, Any] = {
    "project": {
        "name": "bus-test",
        "discount_rate_nominal": 0.08,
    },
    "location": {
        "latitude": 37.77,
        "longitude": -122.42,
        "timezone": "America/Los_Angeles",
    },
    "weather": {"source": "csv", "csv_path": "dummy.csv"},
    "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
    "components": {
        "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
        "grid": {"capacity_kw": 100.0},
    },
    "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.12}},
}


def _make_scenario(**component_overrides: Any) -> Scenario:
    import copy

    data = copy.deepcopy(_BASE_SCENARIO)
    data["components"].update(component_overrides)
    return Scenario.model_validate(data)


def _fresh_es() -> solph.EnergySystem:
    """Return a bare EnergySystem (no timeindex needed for bus creation tests)."""
    import pandas as pd

    timeindex = pd.date_range("2024-01-01", periods=8760, freq="h")
    return solph.EnergySystem(timeindex=timeindex, infer_last_interval=True)


# ---------------------------------------------------------------------------
# BusSet dataclass
# ---------------------------------------------------------------------------


class TestBusSet:
    def test_ac_required(self) -> None:
        """BusSet must have a non-None ac field."""
        ac = solph.Bus(label="ac_bus")
        bs = BusSet(ac=ac)
        assert bs.ac is ac

    def test_defaults_dc_fuel_none(self) -> None:
        bs = BusSet(ac=solph.Bus(label="ac_bus"))
        assert bs.dc is None
        assert bs.fuel is None

    def test_thermal_defaults_to_empty_set(self) -> None:
        """Default thermal field must be an empty ThermalBusSet."""
        bs = BusSet(ac=solph.Bus(label="ac_bus"))
        assert isinstance(bs.thermal, ThermalBusSet)
        assert bs.thermal.has_heating is False
        assert bs.thermal.has_cooling is False
        assert bs.thermal.has_gas is False

    def test_dc_field_populated(self) -> None:
        dc = solph.Bus(label="dc_bus")
        ac = solph.Bus(label="ac_bus")
        bs = BusSet(ac=ac, dc=dc)
        assert bs.dc is dc


# ---------------------------------------------------------------------------
# build_buses — AC bus always created
# ---------------------------------------------------------------------------


class TestBuildBusesAcAlwaysPresent:
    def test_ac_bus_is_always_created(self) -> None:
        """ac_bus must be non-None regardless of component config."""
        scenario = _make_scenario()
        es = _fresh_es()
        bus_set = build_buses(scenario, es)
        assert bus_set.ac is not None

    def test_ac_bus_label(self) -> None:
        scenario = _make_scenario()
        es = _fresh_es()
        bus_set = build_buses(scenario, es)
        assert bus_set.ac.label == "ac_bus"

    def test_ac_bus_added_to_energy_system(self) -> None:
        scenario = _make_scenario()
        es = _fresh_es()
        build_buses(scenario, es)
        assert "ac_bus" in es.groups


# ---------------------------------------------------------------------------
# build_buses — DC bus conditionality (O2 rule)
# ---------------------------------------------------------------------------


class TestBuildBusesDcConditionality:
    def test_no_pv_no_battery_dc_bus_absent(self) -> None:
        """Grid-only scenario without PV or battery must NOT create dc_bus."""
        scenario = _make_scenario()
        es = _fresh_es()
        bus_set = build_buses(scenario, es)
        assert bus_set.dc is None

    def test_no_pv_no_battery_dc_not_in_groups(self) -> None:
        scenario = _make_scenario()
        es = _fresh_es()
        build_buses(scenario, es)
        assert "dc_bus" not in es.groups

    def test_pv_enabled_creates_dc_bus(self) -> None:
        """pv.enabled=True → dc_bus must be created (PV is DC-coupled)."""
        scenario = _make_scenario(pv={"capex_per_kw": 1000.0, "capacity_kw": 100.0})
        es = _fresh_es()
        bus_set = build_buses(scenario, es)
        assert bus_set.dc is not None
        assert bus_set.dc.label == "dc_bus"

    def test_pv_enabled_dc_bus_in_es_groups(self) -> None:
        scenario = _make_scenario(pv={"capex_per_kw": 1000.0, "capacity_kw": 100.0})
        es = _fresh_es()
        build_buses(scenario, es)
        assert "dc_bus" in es.groups

    def test_battery_only_creates_dc_bus(self) -> None:
        """battery.enabled=True (no PV) → dc_bus still created."""
        scenario = _make_scenario(
            battery={
                "capex_per_kwh": 300.0,
            }
        )
        es = _fresh_es()
        bus_set = build_buses(scenario, es)
        assert bus_set.dc is not None

    def test_wind_only_no_dc_bus(self) -> None:
        """Wind turbine is AC-coupled → no dc_bus needed when only wind + grid."""
        scenario = _make_scenario(
            wind_turbine={"turbine_model": "E-53/800", "capex_per_unit": 800_000.0}
        )
        es = _fresh_es()
        bus_set = build_buses(scenario, es)
        assert bus_set.dc is None


# ---------------------------------------------------------------------------
# build_buses — fuel bus NOT pre-created (DieselBuilder owns it)
# ---------------------------------------------------------------------------


class TestBuildBusesFuelBus:
    def test_fuel_bus_not_created_even_with_diesel(self) -> None:
        """Phase 19: fuel_bus is owned by DieselBuilder; build_buses must not add it."""
        scenario = _make_scenario(
            diesel_generator={
                "capacity_kw": 50.0,
                "capex_per_kw": 400.0,
                "fuel_price_per_l": 1.5,
            }
        )
        es = _fresh_es()
        bus_set = build_buses(scenario, es)
        assert bus_set.fuel is None
        assert "fuel_bus" not in es.groups


# ---------------------------------------------------------------------------
# build_buses — thermal buses delegated correctly
# ---------------------------------------------------------------------------


class TestBuildBusesThermal:
    def test_no_thermal_components_no_thermal_buses(self) -> None:
        scenario = _make_scenario()
        es = _fresh_es()
        bus_set = build_buses(scenario, es)
        assert bus_set.thermal.has_heating is False
        assert bus_set.thermal.has_cooling is False
        assert bus_set.thermal.has_gas is False

    def test_heat_pump_creates_thermal_buses(self) -> None:
        scenario = _make_scenario(heat_pump={"enabled": True})
        es = _fresh_es()
        bus_set = build_buses(scenario, es)
        assert bus_set.thermal.has_heating is True
        assert bus_set.thermal.has_cooling is True
        assert "heat_bus" in es.groups
        assert "cool_bus" in es.groups

    def test_gas_supply_creates_heat_and_gas_buses(self) -> None:
        scenario = _make_scenario(gas_supply={"enabled": True})
        es = _fresh_es()
        bus_set = build_buses(scenario, es)
        assert bus_set.thermal.has_heating is True
        assert bus_set.thermal.has_gas is True
        assert bus_set.thermal.has_cooling is False
        assert "heat_bus" in es.groups
        assert "gas_bus" in es.groups
        assert "cool_bus" not in es.groups
