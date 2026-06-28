"""Unit tests for samba.compiler — CRF helpers, component builders, and
:func:`compile_energy_system`."""

from __future__ import annotations

from typing import Any

import numpy as np
import oemof.solph as solph
import pytest

from samba.compiler import (
    CompilerInputs,
    ConfigurationError,
    compile_energy_system,
    crf,
    ep_costs,
)
from samba.compiler.builders import (
    BatteryBuilder,
    GridBuilder,
    InverterBuilder,
    PVBuilder,
    calc_wind_power_kw,
    get_turbine_rated_kw,
)
from samba.scenario.models import Scenario
from samba.tariff import TariffArrays
from samba.weather import stub_weather as _stub_weather

# ---------------------------------------------------------------------------
# Shared test fixtures / helpers
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(42)
_LOAD_KW = np.ones(8760, dtype=np.float64) * 5.0  # 5 kW flat load
_PV_PROFILE = np.clip(_RNG.random(8760), 0.0, 1.0)  # synthetic hourly fractions
_CBUY = np.full(8760, 0.12, dtype=np.float64)
_CSELL = np.full(8760, 0.06, dtype=np.float64)
_TARIFF = TariffArrays(cbuy=_CBUY, csell=_CSELL, service_charge=np.zeros(12))


def _buses() -> tuple[solph.Bus, solph.Bus]:
    """Return fresh (dc_bus, ac_bus) pair."""
    return solph.Bus(label="dc_bus"), solph.Bus(label="ac_bus")


def _deep_update(base: dict[str, Any], overrides: dict[str, Any]) -> None:
    """Recursively merge *overrides* into *base* (mutates *base*)."""
    for key, val in overrides.items():
        if isinstance(val, dict) and key in base and isinstance(base[key], dict):
            _deep_update(base[key], val)
        else:
            base[key] = val


def _make_scenario(**overrides: Any) -> Scenario:
    """Return a minimal valid :class:`Scenario` with optional field overrides.

    Provides a base scenario with:
    - PV (fixed 100 kW), inverter (fixed 50 kW), grid (100 kW) — always present
    - Flat tariff 0.12 $/kWh
    """
    base: dict[str, Any] = {
        "project": {
            "name": "unit-test",
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
            "pv": {"capex_per_kw": 1000.0, "capacity_kw": 100.0},
            "grid": {"capacity_kw": 100.0},
        },
        "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.12}},
    }
    _deep_update(base, overrides)
    return Scenario.model_validate(base)


def _compiler_inputs(scenario: Scenario, **kwargs: Any) -> CompilerInputs:
    """Build a :class:`CompilerInputs` with sensible defaults."""
    return CompilerInputs(
        scenario=scenario,
        load_kw=kwargs.pop("load_kw", _LOAD_KW.copy()),
        tariff_arrays=kwargs.pop("tariff_arrays", _TARIFF),
        weather=kwargs.pop("weather", _stub_weather()),
        pv_per_kwp=kwargs.pop("pv_per_kwp", _PV_PROFILE.copy()),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# CRF / annualization
# ---------------------------------------------------------------------------


class TestCrf:
    def test_standard_rate(self) -> None:
        """crf(0.08, 25) should be approximately 0.0937."""
        assert crf(0.08, 25) == pytest.approx(0.0937, abs=1e-4)

    def test_zero_rate_special_case(self) -> None:
        """At zero discount rate, CRF = 1 / n (straight-line)."""
        assert crf(0.0, 10) == pytest.approx(0.1)

    def test_zero_rate_various_lifetimes(self) -> None:
        for n in [1, 5, 20, 40]:
            assert crf(0.0, n) == pytest.approx(1.0 / n)

    def test_ep_costs_equals_capex_times_crf(self) -> None:
        assert ep_costs(10_000, 0.08, 25) == pytest.approx(10_000 * crf(0.08, 25))

    def test_ep_costs_zero_rate(self) -> None:
        assert ep_costs(5000, 0.0, 10) == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# PV builder
# ---------------------------------------------------------------------------


class TestPVBuilder:
    def test_investment_mode_has_investment_on_flow(self) -> None:
        """PV in Investment mode should have solph.Investment as nominal_capacity."""
        scenario = _make_scenario(components={"pv": {"capex_per_kw": 1000.0, "capacity_kw": None}})
        dc_bus, ac_bus = _buses()
        nodes = PVBuilder().build(scenario, dc_bus, ac_bus, pv_power_per_kwp=_PV_PROFILE)

        assert len(nodes) == 1
        source = nodes[0]
        flow = list(source.outputs.values())[0]
        assert isinstance(flow.investment, solph.Investment), (
            "Investment mode should store Investment in flow.investment"
        )

    def test_fixed_mode_has_numeric_nominal_capacity(self) -> None:
        """PV in fixed mode should have capacity_kw as numeric nominal_capacity."""
        scenario = _make_scenario(components={"pv": {"capex_per_kw": 1000.0, "capacity_kw": 75.0}})
        dc_bus, ac_bus = _buses()
        nodes = PVBuilder().build(scenario, dc_bus, ac_bus, pv_power_per_kwp=_PV_PROFILE)

        source = nodes[0]
        flow = list(source.outputs.values())[0]
        assert flow.nominal_capacity == pytest.approx(75.0)

    def test_returns_single_source_node(self) -> None:
        scenario = _make_scenario()
        dc_bus, ac_bus = _buses()
        nodes = PVBuilder().build(scenario, dc_bus, ac_bus, pv_power_per_kwp=_PV_PROFILE)
        assert len(nodes) == 1
        assert isinstance(nodes[0], solph.components.Source)

    def test_pv_none_raises(self) -> None:
        """Calling PVBuilder when pv is None should raise ValueError."""
        scenario = _make_scenario(
            components={
                "pv": None,
                "diesel_generator": {
                    "capacity_kw": 10.0,
                    "capex_per_kw": 500.0,
                    "fuel_price_per_l": 1.5,
                },
            }
        )
        dc_bus, ac_bus = _buses()
        with pytest.raises(ValueError, match="pv is None"):
            PVBuilder().build(scenario, dc_bus, ac_bus, pv_power_per_kwp=_PV_PROFILE)


# ---------------------------------------------------------------------------
# Battery builder
# ---------------------------------------------------------------------------


class TestBatteryBuilder:
    def test_investment_mode_has_investment_nominal(self) -> None:
        """Battery Investment mode: GenericStorage.nominal_capacity is Investment."""
        scenario = _make_scenario(
            components={
                "battery": {"capex_per_kwh": 300.0, "capacity_kwh": None},
            }
        )
        dc_bus, ac_bus = _buses()
        nodes = BatteryBuilder().build(scenario, dc_bus, ac_bus)

        assert len(nodes) == 1
        storage = nodes[0]
        assert isinstance(storage.investment, solph.Investment), (
            "Investment mode should store Investment in storage.investment"
        )

    def test_investment_mode_flows_also_have_investment(self) -> None:
        """Input and output flows must carry Investment() in oemof ≥ 0.6.1."""
        scenario = _make_scenario(
            components={
                "battery": {"capex_per_kwh": 300.0, "capacity_kwh": None},
            }
        )
        dc_bus, ac_bus = _buses()
        nodes = BatteryBuilder().build(scenario, dc_bus, ac_bus)
        storage = nodes[0]

        input_flow = list(storage.inputs.values())[0]
        output_flow = list(storage.outputs.values())[0]
        assert isinstance(input_flow.investment, solph.Investment)
        assert isinstance(output_flow.investment, solph.Investment)

    def test_fixed_mode_numeric_nominal(self) -> None:
        scenario = _make_scenario(
            components={
                "battery": {"capex_per_kwh": 300.0, "capacity_kwh": 50.0},
            }
        )
        dc_bus, ac_bus = _buses()
        nodes = BatteryBuilder().build(scenario, dc_bus, ac_bus)
        storage = nodes[0]
        # In oemof 0.6.x, GenericStorage stores capacity as nominal_storage_capacity
        assert storage.nominal_storage_capacity == pytest.approx(50.0)

    def test_returns_single_generic_storage(self) -> None:
        scenario = _make_scenario(
            components={"battery": {"capex_per_kwh": 300.0, "capacity_kwh": 20.0}}
        )
        dc_bus, ac_bus = _buses()
        nodes = BatteryBuilder().build(scenario, dc_bus, ac_bus)
        assert len(nodes) == 1
        assert isinstance(nodes[0], solph.components.GenericStorage)


# ---------------------------------------------------------------------------
# Inverter builder
# ---------------------------------------------------------------------------


class TestInverterBuilder:
    def test_fixed_mode_conversion_factors(self) -> None:
        """Inverter efficiency should be reflected in conversion_factors."""
        scenario = _make_scenario(
            components={
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0, "efficiency": 0.96}
            }
        )
        dc_bus, ac_bus = _buses()
        nodes = InverterBuilder().build(scenario, dc_bus, ac_bus)

        assert len(nodes) == 1
        converter = nodes[0]
        assert isinstance(converter, solph.components.Converter)
        # conversion_factors values are _FakeSequence (scalar-like repeated); extract first
        dc_cf = converter.conversion_factors[dc_bus]
        assert float(dc_cf[0]) == pytest.approx(1.0 / 0.96, rel=1e-6)

    def test_investment_mode_has_investment(self) -> None:
        scenario = _make_scenario(
            components={"inverter": {"capex_per_kw": 200.0, "capacity_kw": None}}
        )
        dc_bus, ac_bus = _buses()
        nodes = InverterBuilder().build(scenario, dc_bus, ac_bus)
        converter = nodes[0]
        output_flow = list(converter.outputs.values())[0]
        # In oemof 0.6.x, Investment is stored in flow.investment
        assert isinstance(output_flow.investment, solph.Investment)


# ---------------------------------------------------------------------------
# Grid builder
# ---------------------------------------------------------------------------


class TestGridBuilder:
    def test_no_export_returns_one_node(self) -> None:
        scenario = _make_scenario(
            components={"grid": {"capacity_kw": 100.0, "export_allowed": False}}
        )
        dc_bus, ac_bus = _buses()
        nodes = GridBuilder().build(scenario, dc_bus, ac_bus, cbuy=_CBUY, csell=_CSELL)
        assert len(nodes) == 1
        assert isinstance(nodes[0], solph.components.Source)

    def test_export_returns_two_nodes(self) -> None:
        scenario = _make_scenario(
            components={
                "grid": {
                    "capacity_kw": 100.0,
                    "export_allowed": True,
                    "export_capacity_kw": 50.0,
                }
            },
            tariff={
                "buy": {"type": "flat", "rate_per_kwh": 0.12},
                "sell": {"type": "flat", "rate_per_kwh": 0.06},
            },
        )
        dc_bus, ac_bus = _buses()
        nodes = GridBuilder().build(scenario, dc_bus, ac_bus, cbuy=_CBUY, csell=_CSELL)
        assert len(nodes) == 2
        assert isinstance(nodes[0], solph.components.Source)
        assert isinstance(nodes[1], solph.components.Sink)

    def test_grid_none_raises(self) -> None:
        scenario = _make_scenario(
            components={
                "grid": None,
                "diesel_generator": {
                    "capacity_kw": 10.0,
                    "capex_per_kw": 500.0,
                    "fuel_price_per_l": 1.5,
                },
            }
        )
        dc_bus, ac_bus = _buses()
        with pytest.raises(ValueError, match="grid is None"):
            GridBuilder().build(scenario, dc_bus, ac_bus, cbuy=_CBUY, csell=_CSELL)


# ---------------------------------------------------------------------------
# Wind utilities
# ---------------------------------------------------------------------------


class TestWindUtilities:
    def test_get_rated_kw_known_model(self) -> None:
        assert get_turbine_rated_kw("generic_10kw") == pytest.approx(10.0)

    def test_get_rated_kw_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown turbine model"):
            get_turbine_rated_kw("nonexistent_turbine")

    def test_calc_wind_power_shape(self) -> None:
        speeds = np.full(8760, 10.0)
        power = calc_wind_power_kw(speeds, "generic_10kw")
        assert power.shape == (8760,)

    def test_below_cut_in_is_zero(self) -> None:
        speeds = np.full(8760, 1.0)  # well below cut-in 2.5 m/s
        power = calc_wind_power_kw(speeds, "generic_10kw")
        assert np.all(power == 0.0)

    def test_above_cut_out_is_zero(self) -> None:
        speeds = np.full(8760, 30.0)  # above cut-out 25 m/s
        power = calc_wind_power_kw(speeds, "generic_10kw")
        assert np.all(power == 0.0)

    def test_at_rated_speed_is_rated_kw(self) -> None:
        speeds = np.full(8760, 12.0)  # exactly rated speed
        power = calc_wind_power_kw(speeds, "generic_10kw")
        assert np.allclose(power, 10.0)


# ---------------------------------------------------------------------------
# compile_energy_system — integration
# ---------------------------------------------------------------------------


class TestCompileEnergySystem:
    def test_returns_energy_system(self) -> None:
        scenario = _make_scenario()
        inputs = _compiler_inputs(scenario)
        es = compile_energy_system(inputs)
        assert isinstance(es, solph.EnergySystem)

    def test_dc_bus_and_ac_bus_present(self) -> None:
        scenario = _make_scenario()
        inputs = _compiler_inputs(scenario)
        es = compile_energy_system(inputs)
        labels = {node.label for node in es.nodes}
        assert "dc_bus" in labels
        assert "ac_bus" in labels

    def test_load_sink_present(self) -> None:
        scenario = _make_scenario()
        inputs = _compiler_inputs(scenario)
        es = compile_energy_system(inputs)
        labels = {node.label for node in es.nodes}
        assert "load" in labels

    def test_pv_node_present(self) -> None:
        scenario = _make_scenario()
        inputs = _compiler_inputs(scenario)
        es = compile_energy_system(inputs)
        labels = {node.label for node in es.nodes}
        assert "pv" in labels

    def test_inverter_present(self) -> None:
        scenario = _make_scenario()
        inputs = _compiler_inputs(scenario)
        es = compile_energy_system(inputs)
        labels = {node.label for node in es.nodes}
        assert "inverter" in labels

    def test_grid_present_when_enabled(self) -> None:
        scenario = _make_scenario()
        inputs = _compiler_inputs(scenario)
        es = compile_energy_system(inputs)
        labels = {node.label for node in es.nodes}
        assert "grid_import" in labels

    def test_grid_absent_when_force_disconnect(self) -> None:
        scenario = _make_scenario(
            components={
                "grid": {"capacity_kw": 100.0},
            },
            constraints={"force_grid_disconnect": True},
        )
        inputs = _compiler_inputs(scenario)
        es = compile_energy_system(inputs)
        labels = {node.label for node in es.nodes}
        assert "grid_import" not in labels

    def test_force_disconnect_no_other_gen_raises(self) -> None:
        """force_grid_disconnect with grid as sole generation source → ConfigurationError."""
        # Only a scenario with no pv/wind/diesel and force_grid_disconnect=True should raise.
        scenario2 = _make_scenario(
            components={"pv": None, "grid": {"capacity_kw": 100.0}},
            constraints={"force_grid_disconnect": True},
        )
        with pytest.raises(ConfigurationError, match="force_grid_disconnect"):
            compile_energy_system(_compiler_inputs(scenario2))

    def test_pv_required_array_missing_raises(self) -> None:
        scenario = _make_scenario()
        inputs = _compiler_inputs(scenario, pv_per_kwp=None)
        with pytest.raises(ValueError, match="pv_per_kwp"):
            compile_energy_system(inputs)

    def test_lpsp_adds_unmet_load_source(self) -> None:
        scenario = _make_scenario(constraints={"max_lpsp": 0.05})
        inputs = _compiler_inputs(scenario)
        es = compile_energy_system(inputs)
        labels = {node.label for node in es.nodes}
        assert "unmet_load" in labels

    def test_no_lpsp_no_unmet_load_source(self) -> None:
        scenario = _make_scenario()  # default max_lpsp=0.0
        inputs = _compiler_inputs(scenario)
        es = compile_energy_system(inputs)
        labels = {node.label for node in es.nodes}
        assert "unmet_load" not in labels

    def test_battery_nodes_present_when_enabled(self) -> None:
        scenario = _make_scenario(
            components={"battery": {"capex_per_kwh": 300.0, "capacity_kwh": 20.0}}
        )
        inputs = _compiler_inputs(scenario)
        es = compile_energy_system(inputs)
        labels = {node.label for node in es.nodes}
        assert "battery" in labels

    def test_pv_only_off_grid_compiles(self) -> None:
        """PV-only scenario (no battery, no grid) must compile without error."""
        scenario = _make_scenario(
            components={
                "pv": {"capex_per_kw": 1000.0, "capacity_kw": 50.0},
                "grid": None,
                "battery": None,
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                "diesel_generator": {
                    "capacity_kw": 10.0,
                    "capex_per_kw": 500.0,
                    "fuel_price_per_l": 1.5,
                },
            }
        )
        inputs = _compiler_inputs(scenario)
        es = compile_energy_system(inputs)
        assert isinstance(es, solph.EnergySystem)
