# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for GasSupplyBuilder (Phase 23).

Tests that the builder produces exactly two correctly configured oemof nodes
(a Source and a Converter) given a valid scenario + bus set.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import oemof.solph as solph
import pytest

from samba.compiler.builders.gas_supply import GasSupplyBuilder
from samba.scenario.models import GasSupply, GasTariff

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bus(label: str) -> solph.Bus:
    return solph.Bus(label=label)


def _make_scenario(
    boiler_efficiency: float = 0.90,
    max_output_kw_th: float | None = None,
    emissions_weight: float = 0.0,
) -> MagicMock:
    """Return a minimal mock Scenario with GasSupply configured."""
    sc = MagicMock()
    gs = GasSupply(
        enabled=True,
        boiler_efficiency=boiler_efficiency,
        max_output_kw_th=max_output_kw_th,
        tariff=GasTariff(rate_type="flat", flat_rate=0.04),
    )
    sc.components.gas_supply = gs
    obj = MagicMock()
    obj.emissions_weight = emissions_weight
    sc.objective = obj
    return sc


def _make_bus_set(gas_bus: solph.Bus | None, heat_bus: solph.Bus | None) -> MagicMock:
    bs = MagicMock()
    bs.thermal.gas = gas_bus
    bs.thermal.heating = heat_bus
    return bs


def _gas_rate(n: int = 8760, rate: float = 0.04) -> np.ndarray:
    return np.full(n, rate)


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestGasSupplyBuilderHappy:
    def test_returns_two_nodes(self) -> None:
        sc = _make_scenario()
        gas_bus = _make_bus("gas_bus")
        heat_bus = _make_bus("heat_bus")
        bs = _make_bus_set(gas_bus, heat_bus)

        nodes = GasSupplyBuilder().build(sc, bs, _gas_rate())
        assert len(nodes) == 2

    def test_first_node_is_source_labelled_gas_supply(self) -> None:
        sc = _make_scenario()
        gas_bus = _make_bus("gas_bus")
        heat_bus = _make_bus("heat_bus")
        bs = _make_bus_set(gas_bus, heat_bus)

        nodes = GasSupplyBuilder().build(sc, bs, _gas_rate())
        source = nodes[0]
        assert isinstance(source, solph.components.Source)
        assert source.label == "gas_supply"

    def test_second_node_is_converter_labelled_gas_boiler(self) -> None:
        sc = _make_scenario()
        gas_bus = _make_bus("gas_bus")
        heat_bus = _make_bus("heat_bus")
        bs = _make_bus_set(gas_bus, heat_bus)

        nodes = GasSupplyBuilder().build(sc, bs, _gas_rate())
        boiler = nodes[1]
        assert isinstance(boiler, solph.components.Converter)
        assert boiler.label == "gas_boiler"

    def test_source_outputs_to_gas_bus(self) -> None:
        sc = _make_scenario()
        gas_bus = _make_bus("gas_bus")
        heat_bus = _make_bus("heat_bus")
        bs = _make_bus_set(gas_bus, heat_bus)

        nodes = GasSupplyBuilder().build(sc, bs, _gas_rate())
        source = nodes[0]
        assert gas_bus in source.outputs

    def test_boiler_inputs_from_gas_bus_outputs_to_heat_bus(self) -> None:
        sc = _make_scenario()
        gas_bus = _make_bus("gas_bus")
        heat_bus = _make_bus("heat_bus")
        bs = _make_bus_set(gas_bus, heat_bus)

        nodes = GasSupplyBuilder().build(sc, bs, _gas_rate())
        boiler = nodes[1]
        assert gas_bus in boiler.inputs
        assert heat_bus in boiler.outputs

    def test_boiler_conversion_factor_matches_efficiency(self) -> None:
        efficiency = 0.85
        sc = _make_scenario(boiler_efficiency=efficiency)
        gas_bus = _make_bus("gas_bus")
        heat_bus = _make_bus("heat_bus")
        bs = _make_bus_set(gas_bus, heat_bus)

        nodes = GasSupplyBuilder().build(sc, bs, _gas_rate())
        boiler = nodes[1]
        # oemof stores conversion_factors off the node
        cf = boiler.conversion_factors
        # key is the output bus (heat_bus)
        assert heat_bus in cf
        assert cf[heat_bus][0] == pytest.approx(efficiency)


# ---------------------------------------------------------------------------
# Guard / error tests
# ---------------------------------------------------------------------------


class TestGasSupplyBuilderGuards:
    def test_raises_when_gas_bus_is_none(self) -> None:
        sc = _make_scenario()
        heat_bus = _make_bus("heat_bus")
        bs = _make_bus_set(None, heat_bus)  # gas bus missing
        with pytest.raises(ValueError, match="gas bus is None"):
            GasSupplyBuilder().build(sc, bs, _gas_rate())

    def test_raises_when_heat_bus_is_none(self) -> None:
        sc = _make_scenario()
        gas_bus = _make_bus("gas_bus")
        bs = _make_bus_set(gas_bus, None)  # heat bus missing
        with pytest.raises(ValueError, match="heating bus is None"):
            GasSupplyBuilder().build(sc, bs, _gas_rate())


# ---------------------------------------------------------------------------
# Max output constraint test
# ---------------------------------------------------------------------------


class TestGasSupplyBuilderMaxOutput:
    def test_nominal_capacity_set_on_source_when_max_output_specified(self) -> None:
        boiler_eff = 0.90
        max_kw_th = 100.0
        sc = _make_scenario(boiler_efficiency=boiler_eff, max_output_kw_th=max_kw_th)
        gas_bus = _make_bus("gas_bus")
        heat_bus = _make_bus("heat_bus")
        bs = _make_bus_set(gas_bus, heat_bus)

        nodes = GasSupplyBuilder().build(sc, bs, _gas_rate())
        source = nodes[0]
        flow: solph.Flow = source.outputs[gas_bus]
        # nominal_capacity should equal max_output_kw_th / boiler_efficiency
        expected_max_gas_kw = max_kw_th / boiler_eff
        assert flow.nominal_capacity == pytest.approx(expected_max_gas_kw)


# ---------------------------------------------------------------------------
# Emissions adjustment test
# ---------------------------------------------------------------------------


class TestGasSupplyBuilderEmissions:
    def test_emissions_adjustment_adds_to_rate(self) -> None:
        base_rate = 0.04
        co2_per_kwh = 0.205
        emissions_weight = 10.0  # $/kg CO2
        sc = _make_scenario(emissions_weight=emissions_weight)
        gas_bus = _make_bus("gas_bus")
        heat_bus = _make_bus("heat_bus")
        bs = _make_bus_set(gas_bus, heat_bus)

        rate_arr = _gas_rate(rate=base_rate)
        nodes = GasSupplyBuilder().build(sc, bs, rate_arr)
        source = nodes[0]
        flow: solph.Flow = source.outputs[gas_bus]
        # effective_rate = rate + emissions_weight * co2_per_kwh
        expected_rate = base_rate + emissions_weight * co2_per_kwh
        assert np.allclose(flow.variable_costs, expected_rate, rtol=1e-4)
