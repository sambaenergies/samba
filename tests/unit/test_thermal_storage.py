# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for Phase 21 thermal storage.

Tests cover:
  - ThermalStorage Pydantic schema validation (ThermalStorage model in
    ``samba.scenario.models._components``).
  - ThermalStorageBuilder node construction (investment and fixed sizing, error
    guards for missing buses, cooling storage path).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_SCENARIO: dict[str, Any] = {
    "project": {
        "name": "ts-test",
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
        "heat_pump": {"enabled": True, "mode": "both"},
    },
    "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.12}},
}


def _make_scenario(**ts_kwargs: Any) -> Any:
    """Build a Scenario with a ThermalStorage component from `ts_kwargs`."""
    from samba.scenario.models import Scenario

    data = copy.deepcopy(_BASE_SCENARIO)
    data["components"]["thermal_storage"] = ts_kwargs if ts_kwargs else {"enabled": True}
    return Scenario.model_validate(data)


def _make_bus_set(*, include_cool: bool = True) -> Any:
    """Return a BusSet with thermal buses wired up."""
    import oemof.solph as solph

    from samba.compiler.buses import BusSet
    from samba.thermal.buses import ThermalBusSet

    heat_bus = solph.Bus(label="heat_bus")
    cool_bus = solph.Bus(label="cool_bus") if include_cool else None
    return BusSet(
        ac=solph.Bus(label="ac_bus"),
        thermal=ThermalBusSet(heating=heat_bus, cooling=cool_bus),
    )


def _make_bus_set_no_heating() -> Any:
    """Return a BusSet with NO heating bus (thermal is default empty)."""
    import oemof.solph as solph

    from samba.compiler.buses import BusSet
    from samba.thermal.buses import ThermalBusSet

    return BusSet(ac=solph.Bus(label="ac_bus"), thermal=ThermalBusSet())


# ===========================================================================
# Schema validation
# ===========================================================================


class TestThermalStorageSchema:
    """ThermalStorage Pydantic model validation."""

    def test_default_construction_ok(self) -> None:
        from samba.scenario.models._components import ThermalStorage

        ts = ThermalStorage()
        assert ts.enabled is True
        assert ts.sizing == "investment"
        assert ts.loss_rate_per_hour == pytest.approx(0.002)

    def test_fixed_sizing_requires_capacity(self) -> None:
        from samba.scenario.models._components import ThermalStorage

        with pytest.raises(ValidationError, match="capacity_kwh_th required when sizing='fixed'"):
            ThermalStorage(sizing="fixed")

    def test_fixed_sizing_with_capacity_ok(self) -> None:
        from samba.scenario.models._components import ThermalStorage

        ts = ThermalStorage(sizing="fixed", capacity_kwh_th=50.0)
        assert ts.capacity_kwh_th == 50.0

    def test_loss_rate_at_boundary_ok(self) -> None:
        from samba.scenario.models._components import ThermalStorage

        ts = ThermalStorage(loss_rate_per_hour=0.1)
        assert ts.loss_rate_per_hour == pytest.approx(0.1)

    def test_loss_rate_zero_ok(self) -> None:
        from samba.scenario.models._components import ThermalStorage

        ts = ThermalStorage(loss_rate_per_hour=0.0)
        assert ts.loss_rate_per_hour == 0.0

    def test_loss_rate_above_upper_bound_rejected(self) -> None:
        from samba.scenario.models._components import ThermalStorage

        with pytest.raises(ValidationError, match="loss_rate_per_hour"):
            ThermalStorage(loss_rate_per_hour=0.101)

    def test_loss_rate_negative_rejected(self) -> None:
        from samba.scenario.models._components import ThermalStorage

        with pytest.raises(ValidationError, match="loss_rate_per_hour"):
            ThermalStorage(loss_rate_per_hour=-0.001)

    def test_soc_min_ge_soc_max_rejected(self) -> None:
        from samba.scenario.models._components import ThermalStorage

        with pytest.raises(ValidationError, match="soc_min < soc_max"):
            ThermalStorage(soc_min=0.5, soc_max=0.3)

    def test_soc_min_equal_soc_max_rejected(self) -> None:
        from samba.scenario.models._components import ThermalStorage

        with pytest.raises(ValidationError, match="soc_min < soc_max"):
            ThermalStorage(soc_min=0.4, soc_max=0.4)

    def test_cooling_storage_fixed_requires_cooling_capacity(self) -> None:
        from samba.scenario.models._components import ThermalStorage

        with pytest.raises(ValidationError, match="cooling_capacity_kwh_th required"):
            ThermalStorage(
                sizing="fixed",
                capacity_kwh_th=100.0,
                include_cooling_storage=True,
                # cooling_capacity_kwh_th intentionally omitted
            )

    def test_cooling_storage_fixed_with_capacity_ok(self) -> None:
        from samba.scenario.models._components import ThermalStorage

        ts = ThermalStorage(
            sizing="fixed",
            capacity_kwh_th=100.0,
            include_cooling_storage=True,
            cooling_capacity_kwh_th=50.0,
        )
        assert ts.cooling_capacity_kwh_th == 50.0

    def test_cooling_storage_investment_no_cooling_capacity_ok(self) -> None:
        """Investment mode cooling storage does not require explicit capacity."""
        from samba.scenario.models._components import ThermalStorage

        ts = ThermalStorage(include_cooling_storage=True)
        assert ts.include_cooling_storage is True
        assert ts.sizing == "investment"

    def test_extra_fields_forbidden(self) -> None:
        from samba.scenario.models._components import ThermalStorage

        with pytest.raises(ValidationError):
            ThermalStorage(unknown_field=True)  # type: ignore[call-arg]


# ===========================================================================
# Builder — investment mode
# ===========================================================================


class TestThermalStorageBuilderInvestment:
    """ThermalStorageBuilder with sizing='investment'."""

    def _build(self, *, include_cool: bool = False) -> tuple[Any, list[Any]]:
        from samba.compiler.builders.thermal_storage import ThermalStorageBuilder

        ts_kwargs: dict[str, Any] = {"sizing": "investment"}
        if include_cool:
            ts_kwargs["include_cooling_storage"] = True

        scenario = _make_scenario(**ts_kwargs)
        bus_set = _make_bus_set(include_cool=include_cool)
        nodes = ThermalStorageBuilder().build(scenario, bus_set)
        return scenario, nodes

    def test_returns_one_node_by_default(self) -> None:
        _, nodes = self._build()
        assert len(nodes) == 1

    def test_returns_two_nodes_with_cooling(self) -> None:
        _, nodes = self._build(include_cool=True)
        assert len(nodes) == 2

    def test_heating_node_label(self) -> None:
        _, nodes = self._build()
        assert nodes[0].label == "thermal_storage_heating"

    def test_cooling_node_label(self) -> None:
        _, nodes = self._build(include_cool=True)
        assert nodes[1].label == "thermal_storage_cooling"

    def test_heating_node_nominal_capacity_is_investment(self) -> None:
        import oemof.solph as solph

        _, nodes = self._build()
        assert isinstance(nodes[0].investment, solph.Investment)

    def test_heating_node_input_flow_has_investment(self) -> None:
        import oemof.solph as solph

        _, nodes = self._build()
        node = nodes[0]
        input_flow = next(iter(node.inputs.values()))
        assert isinstance(input_flow.investment, solph.Investment)

    def test_heating_node_output_flow_has_investment(self) -> None:
        import oemof.solph as solph

        _, nodes = self._build()
        node = nodes[0]
        output_flow = next(iter(node.outputs.values()))
        assert isinstance(output_flow.investment, solph.Investment)

    def test_loss_rate_applied(self) -> None:
        """Default loss_rate_per_hour=0.002 is passed to GenericStorage."""
        _, nodes = self._build()
        assert nodes[0].loss_rate[0] == pytest.approx(0.002)


# ===========================================================================
# Builder — fixed mode
# ===========================================================================


class TestThermalStorageBuilderFixed:
    """ThermalStorageBuilder with sizing='fixed'."""

    _CAPACITY = 80.0
    _CHARGE_MAX = 20.0

    def _build(self) -> tuple[Any, list[Any]]:
        from samba.compiler.builders.thermal_storage import ThermalStorageBuilder

        scenario = _make_scenario(
            sizing="fixed",
            capacity_kwh_th=self._CAPACITY,
            charge_power_max_kw_th=self._CHARGE_MAX,
            discharge_power_max_kw_th=self._CHARGE_MAX,
        )
        bus_set = _make_bus_set()
        nodes = ThermalStorageBuilder().build(scenario, bus_set)
        return scenario, nodes

    def test_returns_one_node(self) -> None:
        _, nodes = self._build()
        assert len(nodes) == 1

    def test_nominal_capacity_is_float(self) -> None:

        _, nodes = self._build()
        assert nodes[0].investment is None
        assert float(nodes[0].nominal_storage_capacity) == pytest.approx(self._CAPACITY)

    def test_input_flow_nominal_capacity_is_float(self) -> None:

        _, nodes = self._build()
        input_flow = next(iter(nodes[0].inputs.values()))
        assert input_flow.investment is None
        assert float(input_flow.nominal_capacity) == pytest.approx(self._CHARGE_MAX)

    def test_loss_rate_applied(self) -> None:
        _, nodes = self._build()
        assert nodes[0].loss_rate[0] == pytest.approx(0.002)


# ===========================================================================
# Builder — error guards
# ===========================================================================


class TestThermalStorageBuilderErrors:
    """ValueError guards in ThermalStorageBuilder."""

    def test_no_heating_bus_raises(self) -> None:
        from samba.compiler.builders.thermal_storage import ThermalStorageBuilder

        scenario = _make_scenario(sizing="investment")
        bus_set = _make_bus_set_no_heating()
        with pytest.raises(ValueError, match="heating bus"):
            ThermalStorageBuilder().build(scenario, bus_set)

    def test_cooling_storage_no_cool_bus_raises(self) -> None:
        from samba.compiler.builders.thermal_storage import ThermalStorageBuilder

        scenario = _make_scenario(sizing="investment", include_cooling_storage=True)
        # BusSet has heating but NO cooling bus
        bus_set = _make_bus_set(include_cool=False)
        with pytest.raises(ValueError, match="cooling bus"):
            ThermalStorageBuilder().build(scenario, bus_set)

    def test_disabled_raises_value_error(self) -> None:
        from samba.compiler.builders.thermal_storage import ThermalStorageBuilder

        scenario = _make_scenario(enabled=False)
        bus_set = _make_bus_set()
        with pytest.raises(ValueError):
            ThermalStorageBuilder().build(scenario, bus_set)
