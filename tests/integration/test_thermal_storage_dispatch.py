# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Integration tests for Phase 21 thermal buffer storage.

These tests compile and solve real LP problems using HiGHS.  They are
skipped automatically when HiGHS is not available.

What is tested here:

- The scenario compiles and solves to optimality when thermal storage is enabled.
- All expected TS dispatch columns are present in the DispatchResult.
- The TS capacity keys appear in ``DispatchResult.capacities``.
- Fixed-sizing variant compiles and solves.
- Cooling storage variant compiles and solves.
- Regression: no-thermal / electrical-only scenarios are unaffected.
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
# Shared constants
# ---------------------------------------------------------------------------

_N = 8760
_LOAD_KW = np.full(_N, 3.0, dtype=np.float64)

# Sinusoidal temperature: winter -5 °C, summer 30 °C
_day_of_year = np.arange(_N) / 24.0
_TEMP_C = (12.5 + 17.5 * np.cos(2.0 * np.pi * (_day_of_year - 15.0) / 365.0)).astype(np.float64)

try:
    from samba.tariff import TariffArrays

    _TARIFF_FLAT = TariffArrays(
        cbuy=np.full(_N, 0.20, dtype=np.float64),
        csell=np.full(_N, 0.05, dtype=np.float64),
        service_charge=np.zeros(12),
    )
except Exception:  # pragma: no cover
    _TARIFF_FLAT = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Scenario helpers
# ---------------------------------------------------------------------------


def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> None:
    for k, v in updates.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


def _make_scenario(**overrides: Any) -> Any:
    """Minimal scenario with HP + thermal storage enabled.  Accepts deep-merge overrides."""
    from samba.scenario.models import Scenario

    base: dict[str, Any] = {
        "project": {"name": "ts-integ-test", "discount_rate_nominal": 0.08, "year": 2023},
        "location": {"latitude": 51.5, "longitude": -0.1, "timezone": "Europe/London"},
        "weather": {"source": "csv", "csv_path": "dummy.csv"},
        "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
        "components": {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
            "grid": {"capacity_kw": 50.0},
            "heat_pump": {"enabled": True, "mode": "both"},
            "thermal_storage": {"enabled": True, "sizing": "investment"},
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


# ===========================================================================
# Investment mode (default)
# ===========================================================================


@skip_no_solver
class TestThermalStorageInvestment:
    """Thermal storage with investment sizing (default)."""

    def _build(self) -> tuple[Any, Any]:
        # Use capacity_min_kwh_th=1.0 so the solver is forced to install
        # at least 1 kWh even with the Phase 20/21 placeholder zero thermal demand.
        return _compile_and_solve(
            _make_scenario(
                components={
                    "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                    "grid": {"capacity_kw": 50.0},
                    "heat_pump": {"enabled": True, "mode": "both"},
                    "thermal_storage": {
                        "enabled": True,
                        "sizing": "investment",
                        "capacity_min_kwh_th": 1.0,
                    },
                }
            )
        )

    def test_solves_without_error(self) -> None:
        self._build()

    def test_dispatch_shape(self) -> None:
        _, dr = self._build()
        assert len(dr.dispatch) == _N

    def test_heating_charge_column_present(self) -> None:
        _, dr = self._build()
        assert "thermal_storage_heating_charge_kw" in dr.dispatch.columns

    def test_heating_discharge_column_present(self) -> None:
        _, dr = self._build()
        assert "thermal_storage_heating_discharge_kw" in dr.dispatch.columns

    def test_heating_level_column_present(self) -> None:
        _, dr = self._build()
        assert "thermal_storage_heating_level_kwh_th" in dr.dispatch.columns

    def test_heating_capacity_in_capacities(self) -> None:
        _, dr = self._build()
        assert "thermal_storage_heating_kwh_th" in dr.capacities

    def test_dispatch_non_negative(self) -> None:
        _, dr = self._build()
        assert (dr.dispatch["thermal_storage_heating_charge_kw"] >= -1e-6).all()
        assert (dr.dispatch["thermal_storage_heating_discharge_kw"] >= -1e-6).all()
        assert (dr.dispatch["thermal_storage_heating_level_kwh_th"] >= -1e-6).all()


# ===========================================================================
# Fixed sizing
# ===========================================================================


@skip_no_solver
class TestThermalStorageFixed:
    """Thermal storage with fixed sizing."""

    def _build(self) -> tuple[Any, Any]:
        return _compile_and_solve(
            _make_scenario(
                components={
                    "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                    "grid": {"capacity_kw": 50.0},
                    "heat_pump": {"enabled": True, "mode": "both"},
                    "thermal_storage": {
                        "enabled": True,
                        "sizing": "fixed",
                        "capacity_kwh_th": 50.0,
                        "charge_power_max_kw_th": 10.0,
                        "discharge_power_max_kw_th": 10.0,
                    },
                }
            )
        )

    def test_solves_without_error(self) -> None:
        self._build()

    def test_heating_dispatch_columns_present(self) -> None:
        _, dr = self._build()
        for col in (
            "thermal_storage_heating_charge_kw",
            "thermal_storage_heating_discharge_kw",
            "thermal_storage_heating_level_kwh_th",
        ):
            assert col in dr.dispatch.columns, f"Expected '{col}'"

    def test_heating_capacity_equals_fixed_value(self) -> None:
        _, dr = self._build()
        assert dr.capacities.get("thermal_storage_heating_kwh_th", 0.0) == pytest.approx(
            50.0, abs=1e-3
        )


# ===========================================================================
# Cooling storage variant
# ===========================================================================


@skip_no_solver
class TestThermalStorageWithCooling:
    """Heating + cooling storage (include_cooling_storage=True)."""

    def _build(self) -> tuple[Any, Any]:
        # Use fixed sizing so that both heating and cooling capacities are
        # deterministic and non-zero (investment with no thermal demand would
        # result in 0 capacity chosen by the optimizer).
        return _compile_and_solve(
            _make_scenario(
                components={
                    "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                    "grid": {"capacity_kw": 50.0},
                    "heat_pump": {"enabled": True, "mode": "both"},
                    "thermal_storage": {
                        "enabled": True,
                        "sizing": "fixed",
                        "capacity_kwh_th": 20.0,
                        "include_cooling_storage": True,
                        "cooling_capacity_kwh_th": 10.0,
                    },
                }
            )
        )

    def test_solves_without_error(self) -> None:
        self._build()

    def test_cooling_dispatch_columns_present(self) -> None:
        _, dr = self._build()
        for col in (
            "thermal_storage_cooling_charge_kw",
            "thermal_storage_cooling_discharge_kw",
            "thermal_storage_cooling_level_kwh_th",
        ):
            assert col in dr.dispatch.columns, f"Expected '{col}'"

    def test_cooling_capacity_in_capacities(self) -> None:
        _, dr = self._build()
        assert "thermal_storage_cooling_kwh_th" in dr.capacities
        assert dr.capacities["thermal_storage_cooling_kwh_th"] == pytest.approx(10.0, abs=1e-3)


# ===========================================================================
# Regression: no thermal storage / no HP
# ===========================================================================


@skip_no_solver
class TestRegressionNoThermalStorage:
    """Electrical-only and HP-without-storage scenarios are unaffected."""

    def _build_electrical_only(self) -> tuple[Any, Any]:
        from samba.scenario.models import Scenario

        scenario = Scenario.model_validate(
            {
                "project": {"name": "regression-ts", "discount_rate_nominal": 0.08},
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

    def test_electrical_only_solves(self) -> None:
        self._build_electrical_only()

    def test_no_ts_columns_in_electrical_only(self) -> None:
        _, dr = self._build_electrical_only()
        assert "thermal_storage_heating_charge_kw" not in dr.dispatch.columns
        assert "thermal_storage_heating_level_kwh_th" not in dr.dispatch.columns

    def test_hp_without_storage_solves(self) -> None:
        """HP scenario WITHOUT thermal_storage should still compile fine."""
        from samba.scenario.models import Scenario

        scenario = Scenario.model_validate(
            {
                "project": {"name": "hp-no-ts", "discount_rate_nominal": 0.08},
                "location": {"latitude": 51.5, "longitude": -0.1, "timezone": "Europe/London"},
                "weather": {"source": "csv", "csv_path": "dummy.csv"},
                "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
                "components": {
                    "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                    "grid": {"capacity_kw": 50.0},
                    "heat_pump": {"enabled": True, "mode": "both"},
                },
                "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.20}},
            }
        )
        _compile_and_solve(scenario)

    def test_no_ts_columns_without_ts(self) -> None:
        from samba.scenario.models import Scenario

        scenario = Scenario.model_validate(
            {
                "project": {"name": "hp-no-ts2", "discount_rate_nominal": 0.08},
                "location": {"latitude": 51.5, "longitude": -0.1, "timezone": "Europe/London"},
                "weather": {"source": "csv", "csv_path": "dummy.csv"},
                "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
                "components": {
                    "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                    "grid": {"capacity_kw": 50.0},
                    "heat_pump": {"enabled": True, "mode": "both"},
                },
                "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.20}},
            }
        )
        _, dr = _compile_and_solve(scenario)
        assert "thermal_storage_heating_charge_kw" not in dr.dispatch.columns
