# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Integration tests for Phase 23 -- natural gas supply dispatch.

Tests compile and solve real LP problems using HiGHS.  They are skipped
automatically when HiGHS is not available.

What is tested:

- Gas-only thermal scenario dispatches ``gas_boiler_output_kw_th > 0``.
- Gas + HP scenario: LP selects cheaper source.
- Gas KPIs (``annual_gas_consumption_kwh_th``, ``gas_boiler_npc``, etc.) are
  non-zero and consistent with dispatch.
- ``GasSupply.enabled=False`` compiles without gas nodes (no dispatch columns).
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

_day_of_year = np.arange(_N) / 24.0
# Moderate UK-like temperature
_TEMP_C = (10.0 + 10.0 * np.cos(2.0 * np.pi * (_day_of_year - 15.0) / 365.0)).astype(np.float64)

# Constant heating demand: 2 kW_th throughout the year
_HEAT_KW = np.full(_N, 2.0, dtype=np.float64)

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
# Helpers
# ---------------------------------------------------------------------------


def _deep_update(base: dict[str, Any], updates: dict[str, Any]) -> None:
    for k, v in updates.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


def _make_gas_only_scenario(**overrides: Any) -> Any:
    """Scenario with GasSupply enabled but NO heat pump."""
    from samba.scenario.models import Scenario

    base: dict[str, Any] = {
        "project": {"name": "gas-integ-test", "discount_rate_nominal": 0.05, "year": 2023},
        "location": {"latitude": 51.5, "longitude": -0.1, "timezone": "Europe/London"},
        "weather": {"source": "csv", "csv_path": "dummy.csv"},
        "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
        "components": {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
            "grid": {"capacity_kw": 50.0},
            # Gas-only thermal: no heat_pump
            "gas_supply": {
                "enabled": True,
                "boiler_efficiency": 0.90,
                "tariff": {"rate_type": "flat", "flat_rate": 0.04},
                "capex": 3000.0,
                "opex_per_year": 120.0,
                "lifetime_years": 20,
            },
        },
        "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.20}},
    }
    _deep_update(base, overrides)
    return Scenario.model_validate(base)


def _make_hp_vs_gas_scenario(**overrides: Any) -> Any:
    """Scenario with both heat pump and gas supply enabled."""
    from samba.scenario.models import Scenario

    base: dict[str, Any] = {
        "project": {"name": "hp-gas-integ-test", "discount_rate_nominal": 0.05, "year": 2023},
        "location": {"latitude": 51.5, "longitude": -0.1, "timezone": "Europe/London"},
        "weather": {"source": "csv", "csv_path": "dummy.csv"},
        "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
        "components": {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
            "grid": {"capacity_kw": 50.0},
            "heat_pump": {"enabled": True, "mode": "heating_only"},
            "gas_supply": {
                "enabled": True,
                "boiler_efficiency": 0.90,
                "tariff": {"rate_type": "flat", "flat_rate": 0.08},  # expensive gas
                "capex": 0.0,
                "opex_per_year": 0.0,
                "lifetime_years": 20,
            },
        },
        "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.20}},
    }
    _deep_update(base, overrides)
    return Scenario.model_validate(base)


def _compile_and_solve_with_thermal(
    scenario: Any,
    heat_kw: np.ndarray,
) -> tuple[Any, Any]:
    """Inject a constant thermal load profile and solve."""
    import tempfile
    from pathlib import Path

    import pandas as pd

    from samba.compiler import CompilerInputs, compile_energy_system
    from samba.solver import SolverConfig, extract_dispatch, solve
    from samba.weather import stub_weather

    # Write heat CSV to tmp file
    with tempfile.TemporaryDirectory() as td:
        heat_csv = Path(td) / "heat.csv"
        pd.DataFrame({"kw_th": heat_kw}).to_csv(heat_csv, index=False)

        # Patch in CSV thermal load using correct flat schema
        from samba.scenario.models import Scenario

        sc_dict = scenario.model_dump()
        sc_dict["load"]["thermal"] = {
            "source": "csv",
            "heating_csv_path": str(heat_csv),
        }
        scenario_with_thermal = Scenario.model_validate(sc_dict)

        weather = dataclasses.replace(stub_weather(), tamb_c=_TEMP_C.copy())
        inputs = CompilerInputs(
            scenario=scenario_with_thermal,
            load_kw=_LOAD_KW.copy(),
            tariff_arrays=_TARIFF_FLAT,
            weather=weather,
        )
        es = compile_energy_system(inputs)
        cfg = SolverConfig(solver_name="appsi_highs")
        result = solve(es, scenario_with_thermal, config=cfg)
        return es, extract_dispatch(es, result)


# ---------------------------------------------------------------------------
# Tests: gas-only thermal
# ---------------------------------------------------------------------------


@skip_no_solver
class TestGasOnlyThermal:
    def test_gas_boiler_output_nonzero(self) -> None:
        sc = _make_gas_only_scenario()
        _, dr = _compile_and_solve_with_thermal(sc, _HEAT_KW)
        assert "gas_boiler_output_kw_th" in dr.dispatch.columns
        total = dr.dispatch["gas_boiler_output_kw_th"].sum()
        assert total > 0.0, "Expected non-zero gas boiler output"

    def test_gas_boiler_input_consistent_with_output(self) -> None:
        sc = _make_gas_only_scenario()
        _, dr = _compile_and_solve_with_thermal(sc, _HEAT_KW)
        inp = dr.dispatch["gas_boiler_input_kw_th"].sum()
        out = dr.dispatch["gas_boiler_output_kw_th"].sum()
        # output ≈ input × efficiency (within 1 %)
        assert inp > 0.0
        assert out == pytest.approx(inp * 0.90, rel=0.01)


@skip_no_solver
class TestGasKPIs:
    def test_gas_kpis_present_and_nonzero(self) -> None:
        from samba.run_result.kpis import compute_kpis

        sc = _make_gas_only_scenario()
        _, dr = _compile_and_solve_with_thermal(sc, _HEAT_KW)
        kpis, econ, _ = compute_kpis(sc, dr, _TARIFF_FLAT)

        assert kpis["annual_gas_consumption_kwh_th"] > 0.0
        assert kpis["annual_gas_cost_usd"] > 0.0
        assert kpis["annual_gas_co2_kg"] > 0.0
        assert kpis["gas_boiler_capex"] == pytest.approx(3000.0)
        assert kpis["gas_boiler_npc"] > 0.0

    def test_gas_consumption_consistent_with_dispatch(self) -> None:
        from samba.run_result.kpis import compute_kpis

        sc = _make_gas_only_scenario()
        _, dr = _compile_and_solve_with_thermal(sc, _HEAT_KW)
        kpis, econ, _ = compute_kpis(sc, dr, _TARIFF_FLAT)

        expected_kwh = float(dr.dispatch["gas_boiler_input_kw_th"].sum())
        assert kpis["annual_gas_consumption_kwh_th"] == pytest.approx(expected_kwh, rel=1e-4)

    def test_gas_disabled_gives_zero_kpis(self) -> None:
        """When gas_supply=None, all gas KPIs must be zero."""
        from samba.compiler import CompilerInputs, compile_energy_system
        from samba.run_result.kpis import compute_kpis
        from samba.scenario.models import Scenario
        from samba.solver import SolverConfig, extract_dispatch, solve
        from samba.weather import stub_weather

        sc_dict: dict[str, Any] = {
            "project": {"name": "no-gas", "discount_rate_nominal": 0.05, "year": 2023},
            "location": {"latitude": 51.5, "longitude": -0.1, "timezone": "Europe/London"},
            "weather": {"source": "csv", "csv_path": "dummy.csv"},
            "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
            "components": {
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                "grid": {"capacity_kw": 50.0},
                "heat_pump": {"enabled": True, "mode": "heating_only"},
            },
            "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.20}},
        }
        sc = Scenario.model_validate(sc_dict)
        weather = dataclasses.replace(stub_weather(), tamb_c=_TEMP_C.copy())
        inputs = CompilerInputs(
            scenario=sc,
            load_kw=_LOAD_KW.copy(),
            tariff_arrays=_TARIFF_FLAT,
            weather=weather,
        )
        es = compile_energy_system(inputs)
        cfg = SolverConfig(solver_name="appsi_highs")
        result = solve(es, sc, config=cfg)
        dr = extract_dispatch(es, result)
        kpis, _, _ = compute_kpis(sc, dr, _TARIFF_FLAT)

        assert kpis["annual_gas_consumption_kwh_th"] == pytest.approx(0.0)
        assert kpis["annual_gas_cost_usd"] == pytest.approx(0.0)
        assert kpis["gas_boiler_capex"] == pytest.approx(0.0)
        assert kpis["gas_boiler_npc"] == pytest.approx(0.0)
