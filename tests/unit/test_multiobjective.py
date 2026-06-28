"""Unit tests for Phase 12 multi-objective / cost-and-emissions features.

All tests are pure-Python / NumPy — no solver required.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Economics helpers
# ---------------------------------------------------------------------------


class TestCalcDieselCo2VarCost:
    """Tests for economics.emissions.calc_diesel_co2_var_cost."""

    def test_positive_alpha(self) -> None:
        from samba.economics.emissions import calc_diesel_co2_var_cost

        result = calc_diesel_co2_var_cost(
            co2_per_liter_kg=2.63,
            slope_l_per_kwh=0.246,
            alpha=5.0,
        )
        assert result == pytest.approx(2.63 * 0.246 * 5.0, rel=1e-9)

    def test_zero_alpha_returns_zero(self) -> None:
        from samba.economics.emissions import calc_diesel_co2_var_cost

        assert calc_diesel_co2_var_cost(2.63, 0.246, 0.0) == pytest.approx(0.0)

    def test_zero_slope_returns_zero(self) -> None:
        from samba.economics.emissions import calc_diesel_co2_var_cost

        assert calc_diesel_co2_var_cost(2.63, 0.0, 10.0) == pytest.approx(0.0)

    def test_units_consistent(self) -> None:
        """kg_CO2/L * L/kWh_e * $/kg_CO2 = $/kWh_e."""
        from samba.economics.emissions import calc_diesel_co2_var_cost

        # Result should be in $/kWh_e  — just check sign and scale
        result = calc_diesel_co2_var_cost(2.63, 0.246, 1.0)
        assert 0.0 < result < 5.0  # reasonable $/kWh adder at $1/kg CO2


class TestCalcGridCo2VarCost:
    """Tests for economics.emissions.calc_grid_co2_var_cost."""

    def test_positive_alpha(self) -> None:
        from samba.economics.emissions import calc_grid_co2_var_cost

        result = calc_grid_co2_var_cost(emission_factor_kg_per_kwh=0.4, alpha=10.0)
        assert result == pytest.approx(4.0, rel=1e-9)

    def test_zero_alpha_returns_zero(self) -> None:
        from samba.economics.emissions import calc_grid_co2_var_cost

        assert calc_grid_co2_var_cost(0.4, 0.0) == pytest.approx(0.0)

    def test_zero_emission_factor_returns_zero(self) -> None:
        from samba.economics.emissions import calc_grid_co2_var_cost

        assert calc_grid_co2_var_cost(0.0, 10.0) == pytest.approx(0.0)

    def test_units_consistent(self) -> None:
        """kg_CO2/kWh * $/kg_CO2 = $/kWh."""
        from samba.economics.emissions import calc_grid_co2_var_cost

        result = calc_grid_co2_var_cost(0.4, 50.0)  # $50/kg CO2 is very high
        assert 0.0 < result < 100.0  # stays in reasonable $/kWh territory


# ---------------------------------------------------------------------------
# Scenario model validation
# ---------------------------------------------------------------------------


class TestObjectiveModel:
    """Tests for Objective model changes."""

    def test_cost_type_still_valid(self) -> None:
        from samba.scenario.models import Objective

        obj = Objective(type="cost")
        assert obj.type == "cost"
        assert obj.emissions_weight == 0.0

    def test_cost_and_emissions_type_valid(self) -> None:
        from samba.scenario.models import Objective

        obj = Objective(type="cost_and_emissions", emissions_weight=10.0)
        assert obj.type == "cost_and_emissions"
        assert obj.emissions_weight == pytest.approx(10.0)

    def test_negative_emissions_weight_rejected(self) -> None:
        from samba.scenario.models import Objective

        with pytest.raises(ValidationError):
            Objective(type="cost_and_emissions", emissions_weight=-1.0)

    def test_zero_emissions_weight_valid(self) -> None:
        from samba.scenario.models import Objective

        obj = Objective(type="cost_and_emissions", emissions_weight=0.0)
        assert obj.emissions_weight == 0.0

    def test_invalid_type_rejected(self) -> None:
        from samba.scenario.models import Objective

        with pytest.raises(ValidationError):
            Objective(type="minimise_regret")  # type: ignore[arg-type]


class TestGridEmissionFactor:
    """Tests for Grid.emission_factor_kg_per_kwh field."""

    def test_default_is_zero(self) -> None:
        from samba.scenario.models import Grid

        grid = Grid(capacity_kw=100.0)
        assert grid.emission_factor_kg_per_kwh == 0.0

    def test_positive_value_valid(self) -> None:
        from samba.scenario.models import Grid

        grid = Grid(capacity_kw=100.0, emission_factor_kg_per_kwh=0.4)
        assert grid.emission_factor_kg_per_kwh == pytest.approx(0.4)

    def test_negative_value_rejected(self) -> None:
        from samba.scenario.models import Grid

        with pytest.raises(ValidationError):
            Grid(capacity_kw=100.0, emission_factor_kg_per_kwh=-0.1)


class TestDieselGeneratorCo2Field:
    """Tests for DieselGenerator.co2_per_liter_kg field."""

    def _make_dg(self, **extra: float) -> Any:
        from samba.scenario.models import DieselGenerator

        return DieselGenerator(
            capacity_kw=50.0,
            capex_per_kw=300.0,
            fuel_price_per_l=1.20,
            **extra,  # type: ignore[arg-type]
        )

    def test_default_value(self) -> None:
        dg = self._make_dg()
        assert dg.co2_per_liter_kg == pytest.approx(2.63)

    def test_custom_value(self) -> None:
        dg = self._make_dg(co2_per_liter_kg=2.29)
        assert dg.co2_per_liter_kg == pytest.approx(2.29)

    def test_zero_value_valid(self) -> None:
        """Zero means no CO2 tracking — allowed for testing."""
        dg = self._make_dg(co2_per_liter_kg=0.0)
        assert dg.co2_per_liter_kg == 0.0


class TestSchemaVersionBackwardCompatibility:
    """Legacy scenarios with schema_version 1.0 still parse."""

    def test_schema_1_0_still_parses(self) -> None:
        """A valid scenario with schema_version '1.0' should parse without error.

        All new fields (emissions_weight, emission_factor_kg_per_kwh, co2_per_liter_kg)
        have defaults, so existing YAMLs produced with schema 1.0 still validate.
        """
        from samba.scenario.models import Scenario

        data: dict[str, Any] = {
            "schema_version": "1.0",
            "project": {
                "name": "legacy-test",
                "discount_rate_nominal": 0.08,
            },
            "location": {
                "latitude": 51.5,
                "longitude": -0.1,
                "timezone": "Europe/London",
            },
            "weather": {"source": "csv", "csv_path": "weather.csv"},
            "load": {"source": "hourly_csv", "csv_path": "load.csv"},
            "components": {
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 20.0},
                "grid": {"capacity_kw": 100.0},
            },
            "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.15}},
        }
        scene = Scenario.model_validate(data)
        assert scene.schema_version == "1.0"
        # All Phase 12 fields have defaults
        assert scene.objective.emissions_weight == 0.0
        if scene.components.grid is not None:
            assert scene.components.grid.emission_factor_kg_per_kwh == 0.0


# ---------------------------------------------------------------------------
# Pareto sweep helpers (no solver)
# ---------------------------------------------------------------------------


class TestDefaultAlphaRange:
    """Tests for pareto.sweep.default_alpha_range."""

    def test_length(self) -> None:
        from samba.pareto.sweep import default_alpha_range

        alphas = default_alpha_range(10)
        assert len(alphas) == 10

    def test_first_is_zero(self) -> None:
        from samba.pareto.sweep import default_alpha_range

        alphas = default_alpha_range(5)
        assert alphas[0] == pytest.approx(0.0)

    def test_single_point(self) -> None:
        from samba.pareto.sweep import default_alpha_range

        alphas = default_alpha_range(1)
        assert alphas == [0.0]

    def test_values_positive_after_zero(self) -> None:
        from samba.pareto.sweep import default_alpha_range

        alphas = default_alpha_range(8)
        assert all(a >= 0.0 for a in alphas)
        assert all(alphas[i] < alphas[i + 1] for i in range(1, len(alphas) - 1))

    def test_invalid_n_raises(self) -> None:
        from samba.pareto.sweep import default_alpha_range

        with pytest.raises(ValueError):
            default_alpha_range(0)


class TestMarkDominated:
    """Tests for _mark_dominated helper (NPC-sorted input)."""

    def test_all_non_dominated_when_lem_decreasing(self) -> None:
        from samba.pareto.sweep import ParetoPoint, _mark_dominated

        pts = [
            ParetoPoint(alpha=0.0, npc=100_000, lem=1.0, total_emissions_kg=500),
            ParetoPoint(alpha=1.0, npc=110_000, lem=0.8, total_emissions_kg=400),
            ParetoPoint(alpha=5.0, npc=130_000, lem=0.5, total_emissions_kg=250),
        ]
        _mark_dominated(pts)
        assert not any(p.dominated for p in pts)

    def test_dominated_when_lem_not_decreasing(self) -> None:
        from samba.pareto.sweep import ParetoPoint, _mark_dominated

        pts = [
            ParetoPoint(alpha=0.0, npc=100_000, lem=0.5, total_emissions_kg=250),
            ParetoPoint(alpha=1.0, npc=110_000, lem=0.8, total_emissions_kg=400),  # dominated
            ParetoPoint(alpha=5.0, npc=130_000, lem=0.3, total_emissions_kg=150),
        ]
        _mark_dominated(pts)
        assert not pts[0].dominated
        assert pts[1].dominated
        assert not pts[2].dominated

    def test_empty_list_ok(self) -> None:
        from samba.pareto.sweep import _mark_dominated

        _mark_dominated([])  # no exception


# ---------------------------------------------------------------------------
# Economics __all__ exports
# ---------------------------------------------------------------------------


def test_economics_exports_co2_helpers() -> None:
    """Both new emissions helpers appear in economics.__all__."""
    import samba.economics as econ

    assert "calc_diesel_co2_var_cost" in econ.__all__
    assert "calc_grid_co2_var_cost" in econ.__all__
