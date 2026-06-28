# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for samba.thermal.buses — ThermalBusSet and build_thermal_buses()."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from samba.scenario.models import Scenario
from samba.thermal.buses import ThermalBusSet, build_thermal_buses

# ---------------------------------------------------------------------------
# Minimal scenario factory (no weather/load resolution needed for bus tests)
# ---------------------------------------------------------------------------

_BASE_SCENARIO: dict[str, Any] = {
    "project": {
        "name": "thermal-test",
        "discount_rate_nominal": 0.08,
    },
    "location": {
        "latitude": 51.5,
        "longitude": -0.12,
        "timezone": "Europe/London",
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
    """Build a Scenario with optional components overrides."""
    import copy

    data = copy.deepcopy(_BASE_SCENARIO)
    data["components"].update(component_overrides)
    return Scenario.model_validate(data)


# ---------------------------------------------------------------------------
# ThermalBusSet dataclass
# ---------------------------------------------------------------------------


class TestThermalBusSet:
    def test_defaults_are_none(self) -> None:
        tbs = ThermalBusSet()
        assert tbs.heating is None
        assert tbs.cooling is None
        assert tbs.gas is None

    def test_has_properties_false_when_none(self) -> None:
        tbs = ThermalBusSet()
        assert tbs.has_heating is False
        assert tbs.has_cooling is False
        assert tbs.has_gas is False

    def test_has_properties_true_when_set(self) -> None:
        import oemof.solph as solph

        tbs = ThermalBusSet(
            heating=solph.Bus(label="heat_bus"),
            cooling=solph.Bus(label="cool_bus"),
            gas=solph.Bus(label="gas_bus"),
        )
        assert tbs.has_heating is True
        assert tbs.has_cooling is True
        assert tbs.has_gas is True

    def test_partial_fields(self) -> None:
        import oemof.solph as solph

        tbs = ThermalBusSet(heating=solph.Bus(label="heat_bus"))
        assert tbs.has_heating is True
        assert tbs.has_cooling is False
        assert tbs.has_gas is False


# ---------------------------------------------------------------------------
# build_thermal_buses — creation rules
# ---------------------------------------------------------------------------


class TestBuildThermalBuses:
    def test_no_thermal_components_returns_empty_set(self) -> None:
        """Electrical-only scenario → all three buses are None."""
        scenario = _make_scenario()
        tbs = build_thermal_buses(scenario)
        assert tbs.heating is None
        assert tbs.cooling is None
        assert tbs.gas is None
        assert tbs.has_heating is False
        assert tbs.has_cooling is False
        assert tbs.has_gas is False

    def test_heat_pump_enabled_creates_heat_and_cool_buses(self) -> None:
        """heat_pump.enabled=True → heat_bus and cool_bus created; gas_bus absent."""
        scenario = _make_scenario(heat_pump={"enabled": True})
        tbs = build_thermal_buses(scenario)
        assert tbs.has_heating is True
        assert tbs.has_cooling is True
        assert tbs.has_gas is False

    def test_heat_pump_bus_labels(self) -> None:
        """Buses created for HP have the ADR-001 canonical labels."""
        scenario = _make_scenario(heat_pump={"enabled": True})
        tbs = build_thermal_buses(scenario)
        assert tbs.heating is not None
        assert tbs.cooling is not None
        assert tbs.heating.label == "heat_bus"
        assert tbs.cooling.label == "cool_bus"

    def test_gas_supply_only_creates_heat_and_gas_buses(self) -> None:
        """gas_supply.enabled=True only → heat_bus + gas_bus; no cool_bus."""
        scenario = _make_scenario(gas_supply={"enabled": True})
        tbs = build_thermal_buses(scenario)
        assert tbs.has_heating is True
        assert tbs.has_cooling is False
        assert tbs.has_gas is True

    def test_gas_supply_bus_labels(self) -> None:
        """Gas supply creates buses with correct ADR-001 labels."""
        scenario = _make_scenario(gas_supply={"enabled": True})
        tbs = build_thermal_buses(scenario)
        assert tbs.heating is not None
        assert tbs.gas is not None
        assert tbs.heating.label == "heat_bus"
        assert tbs.gas.label == "gas_bus"

    def test_both_hp_and_gas_enabled(self) -> None:
        """HP + gas supply → all three buses created."""
        scenario = _make_scenario(
            heat_pump={"enabled": True},
            gas_supply={"enabled": True},
        )
        tbs = build_thermal_buses(scenario)
        assert tbs.has_heating is True
        assert tbs.has_cooling is True
        assert tbs.has_gas is True

    def test_heat_pump_disabled_no_buses(self) -> None:
        """heat_pump present but disabled → equivalent to absent."""
        scenario = _make_scenario(heat_pump={"enabled": False})
        tbs = build_thermal_buses(scenario)
        assert tbs.has_heating is False
        assert tbs.has_cooling is False

    def test_gas_supply_disabled_no_gas_bus(self) -> None:
        """gas_supply present but disabled → no gas or heating bus."""
        scenario = _make_scenario(gas_supply={"enabled": False})
        tbs = build_thermal_buses(scenario)
        assert tbs.has_heating is False
        assert tbs.has_gas is False


# ---------------------------------------------------------------------------
# Schema validator — thermal_storage requires a thermal source
# ---------------------------------------------------------------------------


class TestThermalStorageValidator:
    def test_thermal_storage_without_source_raises(self) -> None:
        """thermal_storage alone (no HP, no gas) must raise ValidationError."""
        with pytest.raises(ValidationError, match="thermal_storage requires"):
            _make_scenario(thermal_storage={"enabled": True})

    def test_thermal_storage_with_heat_pump_is_valid(self) -> None:
        """thermal_storage + heat_pump → valid scenario."""
        scenario = _make_scenario(
            heat_pump={"enabled": True},
            thermal_storage={"enabled": True},
        )
        assert scenario.components.thermal_storage is not None

    def test_thermal_storage_with_gas_supply_is_valid(self) -> None:
        """thermal_storage + gas_supply → valid scenario."""
        scenario = _make_scenario(
            gas_supply={"enabled": True},
            thermal_storage={"enabled": True},
        )
        assert scenario.components.thermal_storage is not None

    def test_thermal_storage_disabled_without_source_is_valid(self) -> None:
        """thermal_storage.enabled=False does not trigger the validator."""
        scenario = _make_scenario(thermal_storage={"enabled": False})
        assert scenario.components.thermal_storage is not None
        assert scenario.components.thermal_storage.enabled is False
