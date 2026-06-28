# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for Phase 22 ThermalLoadBuilder.

Tests cover:
  - Heating-only Sink construction (fixed demand profile).
  - Cooling-only Sink construction.
  - Both heating and cooling Sinks.
  - Zero-demand fallback (arrays of zeros).
  - Guard: cooling demand with no cooling bus raises ValueError.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

_HOURS = 8760


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_bus_set(*, include_cool: bool = True) -> Any:
    import oemof.solph as solph

    from samba.compiler.buses import BusSet
    from samba.thermal.buses import ThermalBusSet

    heat_bus = solph.Bus(label="heat_bus")
    cool_bus = solph.Bus(label="cool_bus") if include_cool else None
    return BusSet(
        ac=solph.Bus(label="ac_bus"),
        thermal=ThermalBusSet(heating=heat_bus, cooling=cool_bus),
    )


def _make_bus_set_heat_only() -> Any:
    import oemof.solph as solph

    from samba.compiler.buses import BusSet
    from samba.thermal.buses import ThermalBusSet

    return BusSet(
        ac=solph.Bus(label="ac_bus"),
        thermal=ThermalBusSet(heating=solph.Bus(label="heat_bus"), cooling=None),
    )


def _make_bus_set_no_thermal() -> Any:
    import oemof.solph as solph

    from samba.compiler.buses import BusSet
    from samba.thermal.buses import ThermalBusSet

    return BusSet(
        ac=solph.Bus(label="ac_bus"),
        thermal=ThermalBusSet(),
    )


def _dummy_scenario() -> Any:
    from samba.scenario.models import Scenario

    return Scenario.model_validate(
        {
            "project": {"name": "builder-test", "discount_rate_nominal": 0.08},
            "location": {"latitude": 51.5, "longitude": -0.12, "timezone": "Europe/London"},
            "weather": {"source": "csv", "csv_path": "dummy.csv"},
            "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
            "components": {
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                "grid": {"capacity_kw": 100.0},
            },
            "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.12}},
        }
    )


def _thermal_loads(
    heating: np.ndarray | None = None,
    cooling: np.ndarray | None = None,
) -> Any:
    from samba.load_profiles.thermal import ThermalLoads

    return ThermalLoads(
        heating=heating if heating is not None else np.zeros(_HOURS),
        cooling=cooling if cooling is not None else np.zeros(_HOURS),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestThermalLoadBuilder:
    def _build(
        self,
        *,
        bus_set: Any,
        heating: np.ndarray | None = None,
        cooling: np.ndarray | None = None,
    ) -> list[Any]:
        from samba.compiler.builders.thermal_load import ThermalLoadBuilder

        scenario = _dummy_scenario()
        tl = _thermal_loads(heating=heating, cooling=cooling)
        return ThermalLoadBuilder().build(scenario, bus_set, tl)

    # ---- Heating Sink -------------------------------------------------------

    def test_heating_sink_created(self) -> None:

        bus_set = _make_bus_set_heat_only()
        nodes = self._build(bus_set=bus_set, heating=np.full(_HOURS, 5.0))
        labels = [n.label for n in nodes]
        assert "heat_load" in labels

    def test_heating_sink_is_oemof_sink(self) -> None:
        import oemof.solph as solph

        bus_set = _make_bus_set_heat_only()
        nodes = self._build(bus_set=bus_set, heating=np.full(_HOURS, 5.0))
        heat_sink = next(n for n in nodes if n.label == "heat_load")
        assert isinstance(heat_sink, solph.components.Sink)

    def test_heating_profile_normalised(self) -> None:
        """nominal_capacity == peak; fix values are in [0, 1]."""
        bus_set = _make_bus_set_heat_only()
        profile = np.linspace(0.0, 10.0, _HOURS)
        nodes = self._build(bus_set=bus_set, heating=profile)
        heat_sink = next(n for n in nodes if n.label == "heat_load")
        heat_bus = bus_set.thermal.heating
        flow = heat_sink.inputs[heat_bus]
        assert flow.nominal_capacity == pytest.approx(10.0)
        np.testing.assert_allclose(flow.fix, profile / 10.0, atol=1e-10)

    def test_heating_zero_demand_fallback(self) -> None:
        """All-zero heating array -> zero Sink (bus remains feasible)."""
        import oemof.solph as solph

        bus_set = _make_bus_set_heat_only()
        nodes = self._build(bus_set=bus_set, heating=np.zeros(_HOURS))
        heat_sink = next(n for n in nodes if n.label == "heat_load")
        assert isinstance(heat_sink, solph.components.Sink)
        heat_bus = bus_set.thermal.heating
        flow = heat_sink.inputs[heat_bus]
        assert flow.nominal_capacity == pytest.approx(1.0)

    # ---- Cooling Sink -------------------------------------------------------

    def test_cooling_sink_created(self) -> None:
        bus_set = _make_bus_set(include_cool=True)
        nodes = self._build(bus_set=bus_set, cooling=np.full(_HOURS, 3.0))
        labels = [n.label for n in nodes]
        assert "cool_load" in labels

    def test_cooling_profile_normalised(self) -> None:
        bus_set = _make_bus_set(include_cool=True)
        profile = np.full(_HOURS, 4.0)
        nodes = self._build(bus_set=bus_set, cooling=profile)
        cool_sink = next(n for n in nodes if n.label == "cool_load")
        cool_bus = bus_set.thermal.cooling
        flow = cool_sink.inputs[cool_bus]
        assert flow.nominal_capacity == pytest.approx(4.0)
        np.testing.assert_allclose(flow.fix, np.ones(_HOURS), atol=1e-10)

    # ---- Both ---------------------------------------------------------------

    def test_both_sinks_created(self) -> None:
        bus_set = _make_bus_set(include_cool=True)
        nodes = self._build(
            bus_set=bus_set,
            heating=np.full(_HOURS, 5.0),
            cooling=np.full(_HOURS, 3.0),
        )
        labels = [n.label for n in nodes]
        assert "heat_load" in labels
        assert "cool_load" in labels
        assert len(nodes) == 2

    # ---- Error guard --------------------------------------------------------

    def test_cooling_demand_no_cool_bus_raises(self) -> None:
        bus_set = _make_bus_set_heat_only()  # no cooling bus
        with pytest.raises(ValueError, match="cooling demand is non-zero"):
            self._build(bus_set=bus_set, cooling=np.full(_HOURS, 2.0))

    def test_no_buses_returns_empty(self) -> None:
        bus_set = _make_bus_set_no_thermal()
        nodes = self._build(bus_set=bus_set)
        assert nodes == []
