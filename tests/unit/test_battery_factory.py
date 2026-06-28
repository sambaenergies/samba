"""Unit tests for samba.batteries.factory.build_battery_storage."""

from __future__ import annotations

from typing import Any

import numpy as np
import oemof.solph as solph
import pytest

from samba.batteries.factory import build_battery_storage
from samba.compiler.builders.battery import BatteryBuilder
from samba.scenario.models import Scenario
from samba.tariff import TariffArrays

# ---------------------------------------------------------------------------
# Helpers (mirrors test_compiler.py patterns)
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(0)
_LOAD_KW = np.ones(8760, dtype=np.float64) * 5.0
_PV_PROFILE = np.clip(_RNG.random(8760), 0.0, 1.0)
_TARIFF = TariffArrays(
    cbuy=np.full(8760, 0.12),
    csell=np.zeros(8760),
    service_charge=np.zeros(12),
)


def _buses() -> tuple[solph.Bus, solph.Bus]:
    return solph.Bus(label="dc_bus"), solph.Bus(label="ac_bus")


def _deep_update(base: dict[str, Any], overrides: dict[str, Any]) -> None:
    for key, val in overrides.items():
        if isinstance(val, dict) and key in base and isinstance(base[key], dict):
            _deep_update(base[key], val)
        else:
            base[key] = val


def _make_scenario(**overrides: Any) -> Scenario:
    base: dict[str, Any] = {
        "project": {"name": "factory-test", "discount_rate_nominal": 0.08},
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildBatteryStorage:
    def test_li_ion_returns_single_generic_storage(self) -> None:
        scenario = _make_scenario(
            components={"battery": {"capex_per_kwh": 300.0, "capacity_kwh": 20.0}}
        )
        dc_bus, ac_bus = _buses()
        nodes = build_battery_storage(scenario, dc_bus, ac_bus)
        assert len(nodes) == 1
        assert isinstance(nodes[0], solph.components.GenericStorage)

    def test_li_ion_matches_direct_battery_builder(self) -> None:
        """Factory li_ion result should match the direct BatteryBuilder output."""
        scenario = _make_scenario(
            components={"battery": {"capex_per_kwh": 300.0, "capacity_kwh": 50.0}}
        )
        dc_bus, ac_bus = _buses()
        dc_bus2, ac_bus2 = _buses()

        factory_nodes = build_battery_storage(scenario, dc_bus, ac_bus)
        direct_nodes = BatteryBuilder().build(scenario, dc_bus2, ac_bus2)

        assert len(factory_nodes) == len(direct_nodes) == 1
        fs = factory_nodes[0]
        ds = direct_nodes[0]
        assert fs.nominal_storage_capacity == pytest.approx(ds.nominal_storage_capacity)
        assert fs.inflow_conversion_factor[0] == pytest.approx(ds.inflow_conversion_factor[0])
        assert fs.outflow_conversion_factor[0] == pytest.approx(ds.outflow_conversion_factor[0])

    def test_kibam_returns_single_generic_storage(self) -> None:
        scenario = _make_scenario(
            components={
                "battery": {
                    "capex_per_kwh": 250.0,
                    "capacity_kwh": 20.0,
                    "chemistry": "kibam",
                }
            }
        )
        dc_bus, ac_bus = _buses()
        nodes = build_battery_storage(scenario, dc_bus, ac_bus)
        assert len(nodes) == 1
        assert isinstance(nodes[0], solph.components.GenericStorage)

    def test_kibam_investment_mode_has_investment(self) -> None:
        """KiBaM Investment mode → storage.investment is solph.Investment instance."""
        scenario = _make_scenario(
            components={
                "battery": {
                    "capex_per_kwh": 250.0,
                    "capacity_kwh": None,
                    "chemistry": "kibam",
                }
            }
        )
        dc_bus, ac_bus = _buses()
        nodes = build_battery_storage(scenario, dc_bus, ac_bus)
        storage = nodes[0]
        assert isinstance(storage.investment, solph.Investment)
        # Input and output flows must also carry Investment for oemof ≥ 0.6.1
        input_flow = list(storage.inputs.values())[0]
        output_flow = list(storage.outputs.values())[0]
        assert isinstance(input_flow.investment, solph.Investment)
        assert isinstance(output_flow.investment, solph.Investment)

    def test_kibam_c_rates_lower_than_li_ion_defaults(self) -> None:
        """KiBaM effective C-rate limits should be ≤ li_ion c_rate_charge/discharge defaults."""
        scenario = _make_scenario(
            components={
                "battery": {
                    "capex_per_kwh": 250.0,
                    "capacity_kwh": 20.0,
                    "chemistry": "kibam",
                    "c_rate_charge": 1.0,
                    "c_rate_discharge": 1.0,
                }
            }
        )
        dc_bus, ac_bus = _buses()
        nodes = build_battery_storage(scenario, dc_bus, ac_bus)
        storage = nodes[0]

        # Extract nominal charges from input/output flows
        from samba.batteries.kibam import compute_kibam_limits
        from samba.scenario.models import KiBaMParams

        params = KiBaMParams()
        limits = compute_kibam_limits(params, capacity_kwh=20.0, soc_min=0.2, soc_max=1.0)

        # GenericStorage flow nominal values: charge_kw = capacity * c_rate_ch
        input_flow = list(storage.inputs.values())[0]
        output_flow = list(storage.outputs.values())[0]
        # nominal_capacity on the flow should equal capacity * clamped c_rate
        expected_ch_kw = 20.0 * min(limits["c_rate_ch_limit"], 1.0)
        expected_dch_kw = 20.0 * min(limits["c_rate_dch_limit"], 1.0)
        assert float(input_flow.nominal_capacity) == pytest.approx(expected_ch_kw, rel=1e-6)
        assert float(output_flow.nominal_capacity) == pytest.approx(expected_dch_kw, rel=1e-6)

    def test_kibam_auto_populates_params_when_none(self) -> None:
        """When chemistry=kibam and kibam params are not provided, defaults are used."""
        scenario = _make_scenario(
            components={
                "battery": {
                    "capex_per_kwh": 250.0,
                    "capacity_kwh": 10.0,
                    "chemistry": "kibam",
                }
            }
        )
        bat = scenario.components.battery
        assert bat is not None
        # After model_validator, kibam should be auto-populated with defaults
        assert bat.kibam is not None
        assert bat.kibam.c_ratio == pytest.approx(0.42)
        assert bat.kibam.k_rate == pytest.approx(0.58)

    def test_battery_none_raises(self) -> None:
        scenario = _make_scenario(
            components={
                "battery": None,
                "diesel_generator": {
                    "capacity_kw": 10.0,
                    "capex_per_kw": 500.0,
                    "fuel_price_per_l": 1.5,
                },
            }
        )
        dc_bus, ac_bus = _buses()
        with pytest.raises(ValueError, match="battery is None"):
            build_battery_storage(scenario, dc_bus, ac_bus)
