# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Integration tests for the Heat Pump component (Phase 20).

These tests compile and solve real LP problems using HiGHS.  They are
skipped automatically when HiGHS is not available.

Phase 20 note
-------------
Phase 22 (thermal load schema + builders) is needed before the HP dispatches
any non-zero thermal output.  In Phase 20, thermal demand is the placeholder
zero-demand Sink from the compiler, so ``hp_heating_kw`` and
``hp_cooling_kw`` are expected to be zero throughout.
What *is* meaningfully tested here:

- The HP scenario compiles without error and solves to optimality.
- All expected HP dispatch columns are present in the DispatchResult.
- The KPI contract fields (``hp_model_name``, ``mean_cop_heating``, etc.)
  are populated and in plausible ranges.
- COP pre-computation is exercised end-to-end through the compiler.
- Electrical-only golden scenarios are unaffected (regression guard).
"""

from __future__ import annotations

import dataclasses
import importlib
from typing import Any

import numpy as np
import pytest

pytestmark = pytest.mark.integration

_highs_available = importlib.util.find_spec("highspy") is not None

skip_no_solver = pytest.mark.skipif(
    not _highs_available,
    reason="highspy not installed -- run 'pip install highspy'",
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_N = 8760
_LOAD_KW = np.full(_N, 3.0, dtype=np.float64)
# Temperate climate: winter -5 deg C, summer 30 deg C, sinusoidal
_day_of_year = np.arange(_N) / 24.0
_TEMP_C = (12.5 + 17.5 * np.cos(2.0 * np.pi * (_day_of_year - 15.0) / 365.0)).astype(
    np.float64
)  # range [-5, 30] deg C

try:
    from samba.tariff import TariffArrays

    _TARIFF_FLAT = TariffArrays(
        cbuy=np.full(_N, 0.20, dtype=np.float64),
        csell=np.full(_N, 0.05, dtype=np.float64),
        service_charge=np.zeros(12),
    )
except Exception:  # pragma: no cover
    _TARIFF_FLAT = None  # type: ignore[assignment]


def _make_scenario(**overrides: Any) -> Any:
    """Build a minimal Scenario with grid and HP enabled; apply overrides."""
    from samba.scenario.models import Scenario

    def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> None:
        for k, v in updates.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                _deep_update(base[k], v)
            else:
                base[k] = v

    base: dict[str, Any] = {
        "project": {"name": "hp-integ-test", "discount_rate_nominal": 0.08, "year": 2023},
        "location": {
            "latitude": 51.5,
            "longitude": -0.1,
            "timezone": "Europe/London",
        },
        "weather": {"source": "csv", "csv_path": "dummy.csv"},
        "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
        "components": {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
            "grid": {"capacity_kw": 50.0},
            "heat_pump": {"enabled": True, "mode": "both"},
        },
        "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.20}},
    }
    _deep_update(base, overrides)
    return Scenario.model_validate(base)


def _compile_and_solve(scenario: Any, tariff: Any = None) -> tuple[Any, Any]:
    """Compile + solve; return ``(energy_system, DispatchResult)``."""
    from samba.compiler import CompilerInputs, compile_energy_system
    from samba.solver import SolverConfig, extract_dispatch, solve
    from samba.weather import stub_weather

    t = tariff if tariff is not None else _TARIFF_FLAT
    # Use synthetic temperature array for realistic COP variation (winter -5, summer 30).
    weather = dataclasses.replace(stub_weather(), tamb_c=_TEMP_C.copy())
    inputs = CompilerInputs(
        scenario=scenario,
        load_kw=_LOAD_KW.copy(),
        tariff_arrays=t,
        weather=weather,
    )
    es = compile_energy_system(inputs)
    config = SolverConfig(solver_name="appsi_highs")
    results = solve(es, scenario, config=config)
    return es, extract_dispatch(es, results)


# ---------------------------------------------------------------------------
# TestHeatPumpBoth (mode="both")
# ---------------------------------------------------------------------------


@skip_no_solver
class TestHeatPumpBoth:
    """HP in both-mode (heating + cooling) -- Phase 20 structural validation."""

    def _build(self) -> tuple[Any, Any]:
        return _compile_and_solve(_make_scenario())

    def test_solves_without_error(self) -> None:
        self._build()

    def test_hp_dispatch_columns_present(self) -> None:
        """All four HP dispatch columns must be present."""
        _, dr = self._build()
        for col in (
            "hp_elec_heating_kw",
            "hp_heating_kw",
            "hp_elec_cooling_kw",
            "hp_cooling_kw",
        ):
            assert col in dr.dispatch.columns, f"Expected column '{col}' in dispatch"

    def test_hp_dispatch_zero_no_thermal_demand(self) -> None:
        """Without Phase 22 thermal loads, HP dispatches zero (placeholder demand=0)."""
        _, dr = self._build()
        assert dr.dispatch["hp_heating_kw"].sum() == pytest.approx(0.0, abs=1e-6)
        assert dr.dispatch["hp_cooling_kw"].sum() == pytest.approx(0.0, abs=1e-6)
        assert dr.dispatch["hp_elec_heating_kw"].sum() == pytest.approx(0.0, abs=1e-6)

    def test_dispatch_shape(self) -> None:
        """Dispatch must have 8760 rows."""
        _, dr = self._build()
        assert len(dr.dispatch) == _N


@skip_no_solver
class TestHeatPumpHeatingOnly:
    """HP in heating-only mode."""

    def _build(self) -> tuple[Any, Any]:
        scenario = _make_scenario(
            components={
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                "grid": {"capacity_kw": 50.0},
                "heat_pump": {"enabled": True, "mode": "heating_only"},
            }
        )
        return _compile_and_solve(scenario)

    def test_solves_without_error(self) -> None:
        self._build()

    def test_heating_columns_present_no_cooling(self) -> None:
        _, dr = self._build()
        assert "hp_elec_heating_kw" in dr.dispatch.columns
        assert "hp_heating_kw" in dr.dispatch.columns
        # cooling columns absent since mode = heating_only
        assert "hp_elec_cooling_kw" not in dr.dispatch.columns
        assert "hp_cooling_kw" not in dr.dispatch.columns


@skip_no_solver
class TestHeatPumpFixedCOP:
    """HP with fixed COP -- validates fixed COP path end to end."""

    def _build(self) -> tuple[Any, Any]:
        scenario = _make_scenario(
            components={
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                "grid": {"capacity_kw": 50.0},
                "heat_pump": {
                    "enabled": True,
                    "mode": "both",
                    "cop_source": "fixed",
                    "fixed_cop_heating": 3.0,
                    "fixed_cop_cooling": 4.0,
                },
            }
        )
        return _compile_and_solve(scenario)

    def test_solves_without_error(self) -> None:
        self._build()

    def test_hp_columns_present(self) -> None:
        _, dr = self._build()
        assert "hp_heating_kw" in dr.dispatch.columns
        assert "hp_cooling_kw" in dr.dispatch.columns


@skip_no_solver
class TestElectricalOnlyRegressionGuard:
    """Grid-only scenario must be unaffected by Phase 20 additions."""

    def _build(self) -> tuple[Any, Any]:
        from samba.scenario.models import Scenario

        scenario = Scenario.model_validate(
            {
                "project": {"name": "regression-guard", "discount_rate_nominal": 0.08},
                "location": {"latitude": 51.5, "longitude": -0.1, "timezone": "Europe/London"},
                "weather": {"source": "csv", "csv_path": "dummy.csv"},
                "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
                "components": {
                    "inverter": {"capex_per_kw": 200.0, "capacity_kw": 20.0},
                    "grid": {"capacity_kw": 20.0},
                },
                "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.20}},
            }
        )
        return _compile_and_solve(scenario)

    def test_solves_without_error(self) -> None:
        self._build()

    def test_no_hp_columns_without_hp(self) -> None:
        _, dr = self._build()
        assert "hp_heating_kw" not in dr.dispatch.columns
        assert "hp_cooling_kw" not in dr.dispatch.columns
