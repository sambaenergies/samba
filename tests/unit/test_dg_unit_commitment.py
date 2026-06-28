"""Unit tests for DG unit commitment — schema fields and builder MILP mode.

Fast tests (no solver required, < 1 s each):
  TestDieselGeneratorUCSchema — Pydantic schema validation for new fields
  TestDieselBuilderLP          — builder produces a plain LP flow (no NonConvex)
  TestDieselBuilderMILP        — builder attaches NonConvex when UC fields set
"""

from __future__ import annotations

from typing import Any

import oemof.solph as solph
import pytest
from oemof.solph import NonConvex
from pydantic import ValidationError

from samba.compiler.builders.diesel import DieselBuilder
from samba.scenario.models import DieselGenerator

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_dg(**kwargs: Any) -> DieselGenerator:
    """Return a DieselGenerator with required fields + any overrides."""
    defaults: dict[str, Any] = {
        "capacity_kw": 50.0,
        "capex_per_kw": 400.0,
        "fuel_price_per_l": 1.30,
    }
    defaults.update(kwargs)
    return DieselGenerator(**defaults)


def _make_scenario_with_dg(dg: DieselGenerator) -> Any:
    """Return a minimal Scenario embedding the given DieselGenerator."""
    from samba.scenario.models import (
        BuyRate,
        Components,
        Grid,
        Inverter,
        Load,
        Location,
        Project,
        Scenario,
        Tariff,
        Weather,
    )

    return Scenario(
        project=Project(
            name="uc-unit-test",
            discount_rate_nominal=0.08,
        ),
        location=Location(
            latitude=37.77,
            longitude=-122.42,
            timezone="America/Los_Angeles",
        ),
        weather=Weather(source="csv", csv_path="dummy.csv"),
        load=Load(source="generic_annual_total", annual_kwh=43800.0),
        components=Components(
            inverter=Inverter(capex_per_kw=200.0, capacity_kw=50.0),
            grid=Grid(capacity_kw=100.0),
            diesel_generator=dg,
        ),
        tariff=Tariff(buy=BuyRate(type="flat", rate_per_kwh=0.15)),
    )


def _get_output_flow(nodes: list[solph.network.Node], ac_bus: solph.Bus) -> solph.Flow:
    """Return the output flow of the diesel_generator Converter."""
    for node in nodes:
        if isinstance(node, solph.components.Converter) and node.label == "diesel_generator":
            return node.outputs[ac_bus]
    raise AssertionError("diesel_generator Converter not found in nodes")


def _buses() -> tuple[solph.Bus, solph.Bus]:
    return solph.Bus(label="dc_bus"), solph.Bus(label="ac_bus")


# ---------------------------------------------------------------------------
# TestDieselGeneratorUCSchema
# ---------------------------------------------------------------------------


class TestDieselGeneratorUCSchema:
    """Schema-level tests for the new min_up_hours / min_down_hours / startup_cost fields."""

    # Defaults

    def test_defaults_are_zero(self) -> None:
        dg = _make_dg()
        assert dg.min_up_hours == 0
        assert dg.min_down_hours == 0
        assert dg.startup_cost == 0.0

    # min_up_hours

    def test_min_up_hours_positive_ok(self) -> None:
        dg = _make_dg(min_up_hours=4)
        assert dg.min_up_hours == 4

    def test_min_up_hours_zero_ok(self) -> None:
        dg = _make_dg(min_up_hours=0)
        assert dg.min_up_hours == 0

    def test_min_up_hours_large_ok(self) -> None:
        dg = _make_dg(min_up_hours=8760)
        assert dg.min_up_hours == 8760

    def test_min_up_hours_negative_raises(self) -> None:
        with pytest.raises(ValidationError, match="min_up_hours"):
            _make_dg(min_up_hours=-1)

    # min_down_hours

    def test_min_down_hours_positive_ok(self) -> None:
        dg = _make_dg(min_down_hours=2)
        assert dg.min_down_hours == 2

    def test_min_down_hours_zero_ok(self) -> None:
        dg = _make_dg(min_down_hours=0)
        assert dg.min_down_hours == 0

    def test_min_down_hours_negative_raises(self) -> None:
        with pytest.raises(ValidationError, match="min_down_hours"):
            _make_dg(min_down_hours=-1)

    # startup_cost

    def test_startup_cost_positive_ok(self) -> None:
        dg = _make_dg(startup_cost=25.0)
        assert dg.startup_cost == pytest.approx(25.0)

    def test_startup_cost_zero_ok(self) -> None:
        dg = _make_dg(startup_cost=0.0)
        assert dg.startup_cost == 0.0

    def test_startup_cost_negative_raises(self) -> None:
        with pytest.raises(ValidationError, match="startup_cost"):
            _make_dg(startup_cost=-1.0)

    # Sanity constraint: min_up + min_down <= 8760

    def test_up_plus_down_equal_limit_ok(self) -> None:
        # exact boundary must be OK
        dg = _make_dg(min_up_hours=4380, min_down_hours=4380)
        assert dg.min_up_hours + dg.min_down_hours == 8760

    def test_up_plus_down_exceeds_limit_raises(self) -> None:
        with pytest.raises(ValidationError, match="8760"):
            _make_dg(min_up_hours=5000, min_down_hours=4000)


# ---------------------------------------------------------------------------
# TestDieselBuilderLP — all UC fields at defaults → pure LP (no NonConvex)
# ---------------------------------------------------------------------------


class TestDieselBuilderLP:
    """DieselBuilder.build() with default UC fields produces a plain LP flow."""

    def test_lp_mode_no_nonconvex(self) -> None:
        dc_bus, ac_bus = _buses()
        dg = _make_dg()  # all defaults: min_up/down=0, startup=0, min_load=0
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        assert out_flow.nonconvex is None

    def test_lp_mode_returns_three_nodes(self) -> None:
        dc_bus, ac_bus = _buses()
        dg = _make_dg()
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        assert len(nodes) == 3

    def test_lp_mode_node_labels(self) -> None:
        dc_bus, ac_bus = _buses()
        dg = _make_dg()
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        labels = {n.label for n in nodes}
        assert "diesel_fuel_bus" in labels
        assert "diesel_fuel_source" in labels
        assert "diesel_generator" in labels

    def test_lp_mode_output_capacity(self) -> None:
        dc_bus, ac_bus = _buses()
        dg = _make_dg(capacity_kw=75.0)
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        assert out_flow.nominal_capacity == pytest.approx(75.0)

    def test_min_load_fraction_zero_stays_lp(self) -> None:
        """min_load_fraction=0 is falsy → no NonConvex."""
        dc_bus, ac_bus = _buses()
        dg = _make_dg(min_load_fraction=0.0)
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        assert out_flow.nonconvex is None


# ---------------------------------------------------------------------------
# TestDieselBuilderMILP — NonConvex attached when UC fields non-zero
# ---------------------------------------------------------------------------


class TestDieselBuilderMILP:
    """DieselBuilder.build() attaches NonConvex when UC fields are non-zero."""

    def test_min_up_hours_triggers_milp(self) -> None:
        dc_bus, ac_bus = _buses()
        dg = _make_dg(min_up_hours=4)
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        assert out_flow.nonconvex is not None
        assert isinstance(out_flow.nonconvex, NonConvex)

    def test_min_up_hours_value_on_nonconvex(self) -> None:
        dc_bus, ac_bus = _buses()
        dg = _make_dg(min_up_hours=4)
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        # oemof expands scalar to array
        assert out_flow.nonconvex.minimum_uptime[0] == 4

    def test_min_down_hours_triggers_milp(self) -> None:
        dc_bus, ac_bus = _buses()
        dg = _make_dg(min_down_hours=3)
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        assert out_flow.nonconvex is not None

    def test_min_down_hours_value_on_nonconvex(self) -> None:
        dc_bus, ac_bus = _buses()
        dg = _make_dg(min_down_hours=3)
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        assert out_flow.nonconvex.minimum_downtime[0] == 3

    def test_startup_cost_triggers_milp(self) -> None:
        dc_bus, ac_bus = _buses()
        dg = _make_dg(startup_cost=25.0)
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        assert out_flow.nonconvex is not None

    def test_startup_cost_value_on_nonconvex(self) -> None:
        dc_bus, ac_bus = _buses()
        dg = _make_dg(startup_cost=25.0)
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        assert out_flow.nonconvex.startup_costs[0] == pytest.approx(25.0)

    def test_min_load_fraction_triggers_milp(self) -> None:
        dc_bus, ac_bus = _buses()
        dg = _make_dg(min_load_fraction=0.3)
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        assert out_flow.nonconvex is not None

    def test_milp_all_uc_fields_set(self) -> None:
        """All three UC fields together produce a NonConvex with all attrs."""
        dc_bus, ac_bus = _buses()
        dg = _make_dg(min_up_hours=4, min_down_hours=2, startup_cost=50.0)
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        assert out_flow.nonconvex is not None
        assert out_flow.nonconvex.minimum_uptime[0] == 4
        assert out_flow.nonconvex.minimum_downtime[0] == 2
        assert out_flow.nonconvex.startup_costs[0] == pytest.approx(50.0)

    def test_milp_output_capacity_preserved(self) -> None:
        dc_bus, ac_bus = _buses()
        dg = _make_dg(capacity_kw=80.0, min_up_hours=2)
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        assert out_flow.nominal_capacity == pytest.approx(80.0)

    def test_milp_zero_uptime_downtime_still_lp(self) -> None:
        """Explicitly setting all UC fields to 0 stays LP even in MILP branch."""
        dc_bus, ac_bus = _buses()
        dg = _make_dg(min_up_hours=0, min_down_hours=0, startup_cost=0.0, min_load_fraction=0.0)
        scenario = _make_scenario_with_dg(dg)
        nodes = DieselBuilder().build(scenario, dc_bus, ac_bus)
        out_flow = _get_output_flow(nodes, ac_bus)
        # No NonConvex: pure LP
        assert out_flow.nonconvex is None


# ---------------------------------------------------------------------------
# TestSolverConfigMILP — SolverConfig fields and MILP detection
# ---------------------------------------------------------------------------


class TestSolverConfigMILP:
    """SolverConfig includes milp_time_limit_s and milp_mip_gap fields."""

    def test_default_milp_time_limit(self) -> None:
        from samba.solver.runner import SolverConfig

        cfg = SolverConfig()
        assert cfg.milp_time_limit_s == 1200

    def test_default_milp_mip_gap(self) -> None:
        from samba.solver.runner import SolverConfig

        cfg = SolverConfig()
        assert cfg.milp_mip_gap == pytest.approx(0.02)

    def test_milp_time_limit_greater_than_lp(self) -> None:
        from samba.solver.runner import SolverConfig

        cfg = SolverConfig()
        assert cfg.milp_time_limit_s > cfg.time_limit_s

    def test_custom_milp_fields(self) -> None:
        from samba.solver.runner import SolverConfig

        cfg = SolverConfig(milp_time_limit_s=3600, milp_mip_gap=0.05)
        assert cfg.milp_time_limit_s == 3600
        assert cfg.milp_mip_gap == pytest.approx(0.05)
