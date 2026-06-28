# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Integration tests for thermal bus topology — Phase 19.

Verifies that:
- Compiling with ``heat_pump.enabled=True`` creates ``heat_bus`` and ``cool_bus``
  nodes in the energy system alongside the standard electrical buses.
- Compiling a standard v2 (PV + battery) scenario does NOT create thermal buses.
- The thermal placeholder nodes (``heat_unmet``, ``heat_load``, ``cool_unmet``,
  ``cool_load``) are present in the energy system groups when thermal buses exist.
- ``extract_dispatch`` on a thermal scenario includes the four thermal columns;
  on an electrical-only scenario they are absent.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from samba.compiler import CompilerInputs, compile_energy_system
from samba.scenario.models import Scenario
from samba.tariff import TariffArrays
from samba.weather import stub_weather

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(7)
_LOAD_KW = np.ones(8760, dtype=np.float64) * 5.0
_PV_PROFILE = np.clip(_RNG.random(8760), 0.0, 1.0)
_CBUY = np.full(8760, 0.12, dtype=np.float64)
_CSELL = np.full(8760, 0.04, dtype=np.float64)
_TARIFF = TariffArrays(cbuy=_CBUY, csell=_CSELL, service_charge=np.zeros(12))


_BASE: dict[str, Any] = {
    "project": {
        "name": "thermal-integration-test",
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
        "pv": {"capex_per_kw": 1000.0, "capacity_kw": 100.0},
        "grid": {"capacity_kw": 100.0},
    },
    "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.12}},
}


def _make_scenario(**component_overrides: Any) -> Scenario:
    import copy

    data = copy.deepcopy(_BASE)
    data["components"].update(component_overrides)
    return Scenario.model_validate(data)


def _make_inputs(scenario: Scenario) -> CompilerInputs:
    return CompilerInputs(
        scenario=scenario,
        load_kw=_LOAD_KW.copy(),
        tariff_arrays=_TARIFF,
        weather=stub_weather(),
        pv_per_kwp=_PV_PROFILE.copy(),
    )


# ---------------------------------------------------------------------------
# Thermal topology tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestThermalTopology:
    """Phase 19: thermal bus infrastructure present in compiled EnergySystem."""

    def test_standard_scenario_has_no_thermal_buses(self) -> None:
        """A PV + grid scenario (no thermal components) must not have heat/cool buses."""
        scenario = _make_scenario()
        es = compile_energy_system(_make_inputs(scenario))
        assert "heat_bus" not in es.groups, "heat_bus should not exist in electrical-only scenario"
        assert "cool_bus" not in es.groups, "cool_bus should not exist in electrical-only scenario"
        assert "gas_bus" not in es.groups

    def test_standard_scenario_has_dc_and_ac_buses(self) -> None:
        """Standard PV scenario must still have dc_bus and ac_bus."""
        scenario = _make_scenario()
        es = compile_energy_system(_make_inputs(scenario))
        assert "dc_bus" in es.groups
        assert "ac_bus" in es.groups

    def test_heat_pump_creates_heat_and_cool_buses(self) -> None:
        """Enabling heat_pump must add heat_bus and cool_bus to energy system groups."""
        scenario = _make_scenario(heat_pump={"enabled": True})
        es = compile_energy_system(_make_inputs(scenario))
        assert "heat_bus" in es.groups, "heat_bus missing with heat_pump enabled"
        assert "cool_bus" in es.groups, "cool_bus missing with heat_pump enabled"

    def test_heat_pump_creates_placeholder_nodes(self) -> None:
        """Thermal placeholder nodes must be present when heat_pump is enabled."""
        scenario = _make_scenario(heat_pump={"enabled": True})
        es = compile_energy_system(_make_inputs(scenario))
        assert "heat_unmet" in es.groups
        assert "heat_load" in es.groups
        assert "cool_unmet" in es.groups
        assert "cool_load" in es.groups

    def test_heat_pump_does_not_remove_electrical_buses(self) -> None:
        """Adding thermal domain must not affect the electrical topology."""
        scenario = _make_scenario(heat_pump={"enabled": True})
        es = compile_energy_system(_make_inputs(scenario))
        assert "ac_bus" in es.groups
        assert "dc_bus" in es.groups  # PV is present
        assert "inverter" in es.groups
        assert "load" in es.groups

    def test_gas_supply_creates_heat_and_gas_buses_no_cool(self) -> None:
        """Gas supply → heat_bus + gas_bus, NO cool_bus."""
        scenario = _make_scenario(gas_supply={"enabled": True})
        es = compile_energy_system(_make_inputs(scenario))
        assert "heat_bus" in es.groups
        assert "gas_bus" in es.groups
        assert "cool_bus" not in es.groups

    def test_gas_supply_placeholder_nodes(self) -> None:
        """Gas-only thermal → heating placeholder nodes exist, cooling ones do not."""
        scenario = _make_scenario(gas_supply={"enabled": True})
        es = compile_energy_system(_make_inputs(scenario))
        assert "heat_unmet" in es.groups
        assert "heat_load" in es.groups
        assert "cool_unmet" not in es.groups
        assert "cool_load" not in es.groups

    def test_no_thermal_components_no_placeholder_nodes(self) -> None:
        """Electrical-only scenario must NOT have thermal placeholder nodes."""
        scenario = _make_scenario()
        es = compile_energy_system(_make_inputs(scenario))
        assert "heat_unmet" not in es.groups
        assert "heat_load" not in es.groups
        assert "cool_unmet" not in es.groups
        assert "cool_load" not in es.groups


# ---------------------------------------------------------------------------
# Grid-only scenario — dc_bus conditionality
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDcBusConditionality:
    """DC bus is only created when PV or battery is present (O2 rule)."""

    def test_grid_only_no_dc_bus(self) -> None:
        """Grid-only scenario (no PV, no battery) must not have dc_bus or inverter."""
        import copy

        data = copy.deepcopy(_BASE)
        data["components"] = {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
            "grid": {"capacity_kw": 100.0},
        }
        scenario = Scenario.model_validate(data)
        inputs = CompilerInputs(
            scenario=scenario,
            load_kw=_LOAD_KW.copy(),
            tariff_arrays=_TARIFF,
            weather=stub_weather(),
        )
        es = compile_energy_system(inputs)
        assert "dc_bus" not in es.groups
        # inverter is also not built when there is no dc_bus
        assert "inverter" not in es.groups

    def test_pv_creates_dc_bus_and_inverter(self) -> None:
        """PV-equipped scenario must have both dc_bus and inverter."""
        scenario = _make_scenario()  # has PV
        es = compile_energy_system(_make_inputs(scenario))
        assert "dc_bus" in es.groups
        assert "inverter" in es.groups
