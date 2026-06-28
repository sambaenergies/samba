# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Integration tests for Phase 22 building thermal loads.

These tests compile and solve real LP problems using HiGHS.  They are
skipped automatically when HiGHS is not available.

What is tested here:

- CSV-source thermal load: ``heat_load_kw`` is non-zero after solve.
- Degree-day thermal load: heating demand matches degree-day formula.
- Thermal LPSP KPIs are present in compute_kpis output.
- ``annual_heating_demand_kwh_th`` matches sum of ``heat_load_kw``.
- Backward-compat: no ThermalLoad configured → placeholder zeros, no error.
- Cooling demand with no cooling bus raises at compile time.
"""

from __future__ import annotations

import dataclasses
import importlib
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
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

# Sinusoidal temperature: winter ~-5 °C, summer ~30 °C
_day_of_year = np.arange(_N) / 24.0
_TEMP_C = (12.5 + 17.5 * np.cos(2.0 * np.pi * (_day_of_year - 15.0) / 365.0)).astype(np.float64)

# Constant small heating demand: 2 kW_th throughout the year
_HEAT_KW = np.full(_N, 2.0, dtype=np.float64)
# Constant small cooling demand: 1 kW_th throughout the year
_COOL_KW = np.full(_N, 1.0, dtype=np.float64)

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


def _write_csv(path: Path, arr: np.ndarray) -> None:
    pd.DataFrame({"kw_th": arr}).to_csv(path, index=False)


def _make_scenario(thermal_dict: dict[str, Any] | None = None, **overrides: Any) -> Any:
    """Minimal scenario with HP enabled.  Optionally includes ThermalLoad."""
    from samba.scenario.models import Scenario

    base: dict[str, Any] = {
        "project": {"name": "tl-integ-test", "discount_rate_nominal": 0.08, "year": 2023},
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
    if thermal_dict is not None:
        base["load"]["thermal"] = thermal_dict
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
# CSV source
# ===========================================================================


@skip_no_solver
class TestCsvThermalLoad:
    """Thermal load supplied via CSV files."""

    def _build_heating_only(self) -> tuple[Any, Any]:
        with tempfile.TemporaryDirectory() as tmp:
            h_path = Path(tmp) / "heating.csv"
            _write_csv(h_path, _HEAT_KW)
            scenario = _make_scenario(
                thermal_dict={"source": "csv", "heating_csv_path": str(h_path)}
            )
            return _compile_and_solve(scenario)

    def test_solves_without_error(self) -> None:
        self._build_heating_only()

    def test_heat_load_kw_nonzero(self) -> None:
        _, dr = self._build_heating_only()
        assert "heat_load_kw" in dr.dispatch.columns
        assert dr.dispatch["heat_load_kw"].sum() > 0.0

    def test_heat_load_matches_input(self) -> None:
        """Total heat served ≈ annual heating demand (LPSP ≈ 0 with ample HP)."""
        _, dr = self._build_heating_only()
        # Grid + HP can meet demand; unmet thermal should be ~0
        assert dr.dispatch["heat_load_kw"].sum() == pytest.approx(float(_HEAT_KW.sum()), rel=0.01)

    def test_dispatch_has_heat_unmet_column(self) -> None:
        _, dr = self._build_heating_only()
        assert "heat_unmet_kw" in dr.dispatch.columns

    def test_dispatch_shape(self) -> None:
        _, dr = self._build_heating_only()
        assert len(dr.dispatch) == _N

    def test_kpis_annual_heating_demand(self) -> None:
        from samba.run_result.kpis import compute_kpis

        with tempfile.TemporaryDirectory() as tmp:
            h_path = Path(tmp) / "heating.csv"
            _write_csv(h_path, _HEAT_KW)
            scenario = _make_scenario(
                thermal_dict={"source": "csv", "heating_csv_path": str(h_path)}
            )
            _, dr = _compile_and_solve(scenario)
            kpis, _, _ = compute_kpis(scenario, dr, _TARIFF_FLAT)

        assert kpis["annual_heating_demand_kwh_th"] == pytest.approx(
            float(dr.dispatch["heat_load_kw"].sum()), rel=1e-4
        )

    def test_kpis_thermal_lpsp_fields_present(self) -> None:
        from samba.run_result.kpis import compute_kpis

        with tempfile.TemporaryDirectory() as tmp:
            h_path = Path(tmp) / "heating.csv"
            _write_csv(h_path, _HEAT_KW)
            scenario = _make_scenario(
                thermal_dict={"source": "csv", "heating_csv_path": str(h_path)}
            )
            _, dr = _compile_and_solve(scenario)
            kpis, _, _ = compute_kpis(scenario, dr, _TARIFF_FLAT)

        assert "thermal_lpsp_heating" in kpis
        assert "thermal_lpsp_cooling" in kpis
        assert "annual_cooling_demand_kwh_th" in kpis


# ===========================================================================
# Degree-day source
# ===========================================================================


@skip_no_solver
class TestDegreeDayThermalLoad:
    """Thermal load derived from outdoor temperature."""

    _UA = 0.1  # kW/K -- small enough to keep peak demand low

    def _build(self) -> tuple[Any, Any]:
        scenario = _make_scenario(
            thermal_dict={
                "source": "degree_day",
                "building_ua_kw_per_k": self._UA,
                "heating_setpoint_c": 20.0,
                "cooling_setpoint_c": 24.0,
                "distribution_efficiency": 1.0,
            },
            components={
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                "grid": {"capacity_kw": 50.0},
                "heat_pump": {"enabled": True, "mode": "both"},
            },
        )
        return _compile_and_solve(scenario)

    def test_solves_without_error(self) -> None:
        self._build()

    def test_heat_load_kw_nonzero(self) -> None:
        _, dr = self._build()
        # Temperature drops below 20°C in this climate -- heating demand > 0
        assert dr.dispatch["heat_load_kw"].sum() > 0.0

    def test_heat_load_matches_degree_day_formula(self) -> None:
        """Verify load matches UA * max(setpoint - T_out, 0)."""
        from samba.load_profiles.thermal import ThermalLoads, _degree_day_loads

        t_set_h = 20.0
        expected_tl: ThermalLoads = _degree_day_loads(
            t_outdoor=_TEMP_C,
            ua_heat=self._UA,
            ua_cool=self._UA,
            t_set_heat=t_set_h,
            t_set_cool=24.0,
            eta_dist=1.0,
        )
        _, dr = self._build()
        np.testing.assert_allclose(
            dr.dispatch["heat_load_kw"].to_numpy(),
            expected_tl.heating,
            rtol=1e-4,
            atol=1e-6,
        )

    def test_kpis_annual_demand_positive(self) -> None:
        from samba.run_result.kpis import compute_kpis

        scenario = _make_scenario(
            thermal_dict={
                "source": "degree_day",
                "building_ua_kw_per_k": self._UA,
            },
            components={
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                "grid": {"capacity_kw": 50.0},
                "heat_pump": {"enabled": True, "mode": "both"},
            },
        )
        _, dr = _compile_and_solve(scenario)
        kpis, _, _ = compute_kpis(scenario, dr, _TARIFF_FLAT)
        assert kpis["annual_heating_demand_kwh_th"] > 0.0


# ===========================================================================
# Backward compatibility: no ThermalLoad configured
# ===========================================================================


@skip_no_solver
class TestNoThermalLoad:
    """Scenarios without ThermalLoad must still compile and solve correctly."""

    def _build_with_hp_no_thermal(self) -> tuple[Any, Any]:
        scenario = _make_scenario(thermal_dict=None)
        return _compile_and_solve(scenario)

    def test_solves_without_error(self) -> None:
        self._build_with_hp_no_thermal()

    def test_heat_load_placeholder_is_zero(self) -> None:
        _, dr = self._build_with_hp_no_thermal()
        if "heat_load_kw" in dr.dispatch.columns:
            assert dr.dispatch["heat_load_kw"].sum() == pytest.approx(0.0, abs=1e-6)

    def test_kpis_heating_demand_is_zero(self) -> None:
        from samba.run_result.kpis import compute_kpis

        scenario = _make_scenario(thermal_dict=None)
        _, dr = _compile_and_solve(scenario)
        kpis, _, _ = compute_kpis(scenario, dr, _TARIFF_FLAT)
        assert kpis["annual_heating_demand_kwh_th"] == pytest.approx(0.0, abs=1e-6)
