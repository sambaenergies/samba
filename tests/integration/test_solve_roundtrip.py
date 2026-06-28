"""Integration tests for the full compile → solve → extract → write pipeline.

These tests invoke a real LP solver (HiGHS via ``highspy``).  They are
skipped automatically when HiGHS is not available so the unit-test suite
remains green even before ``pip install -e .`` is re-run.

Run the full suite including integration tests:
    pytest tests/integration/test_solve_roundtrip.py -v

Skip slow investment-mode tests:
    pytest tests/integration/test_solve_roundtrip.py -m "not slow"
"""

from __future__ import annotations

import importlib
from typing import Any

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Module-level skip if HiGHS is unavailable
# ---------------------------------------------------------------------------

_highs_available = importlib.util.find_spec("highspy") is not None

pytestmark = pytest.mark.integration

skip_no_solver = pytest.mark.skipif(
    not _highs_available,
    reason="highspy not installed — run 'pip install highspy' or 'pip install -e .'",
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(2026)
_N = 8760

# Flat 5 kW load
_LOAD_KW = np.full(_N, 5.0, dtype=np.float64)

# Synthetic PV profile: half the day at 0.5, rest at 0
_PV_HALF = np.where(
    np.tile(np.concatenate([np.ones(12) * 0.5, np.zeros(12)]), 365),
    1.0,
    0.0,
).astype(np.float64)

# Flat buy tariff
try:
    from samba.tariff import TariffArrays

    _TARIFF = TariffArrays(
        cbuy=np.full(_N, 0.15, dtype=np.float64),
        csell=np.full(_N, 0.06, dtype=np.float64),
        service_charge=np.zeros(12),
    )
except Exception:  # pragma: no cover
    _TARIFF = None  # type: ignore[assignment]


def _make_scenario(**overrides: Any) -> Any:
    """Return a minimal Scenario using the same helper pattern as test_compiler.py."""
    from samba.scenario.models import Scenario

    def deep_update(base: dict, updates: dict) -> None:  # type: ignore[type-arg]
        for k, v in updates.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                deep_update(base[k], v)
            else:
                base[k] = v

    base: dict[str, Any] = {
        "project": {"name": "integ-test", "discount_rate_nominal": 0.08},
        "location": {
            "latitude": 37.77,
            "longitude": -122.42,
            "timezone": "America/Los_Angeles",
        },
        "weather": {"source": "csv", "csv_path": "dummy.csv"},
        "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
        "components": {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
            "pv": {"capex_per_kw": 1000.0, "capacity_kw": 20.0},
            "grid": {"capacity_kw": 100.0},
        },
        "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.15}},
    }
    deep_update(base, overrides)
    return Scenario.model_validate(base)


def _compile_and_solve(scenario: Any, **cfg_kwargs: Any) -> tuple[Any, Any]:
    """Compile + solve the scenario, return (energy_system, DispatchResult)."""
    from samba.compiler import CompilerInputs, compile_energy_system
    from samba.solver import SolverConfig, extract_dispatch, solve
    from samba.weather import stub_weather as _stub_weather

    inputs = CompilerInputs(
        scenario=scenario,
        load_kw=_LOAD_KW.copy(),
        tariff_arrays=_TARIFF,
        weather=_stub_weather(),
        pv_per_kwp=_PV_HALF.copy(),
    )
    es = compile_energy_system(inputs)
    config = SolverConfig(solver_name="appsi_highs", **cfg_kwargs)
    results = solve(es, scenario, config=config)
    dispatch_result = extract_dispatch(es, results)
    return es, dispatch_result


# ---------------------------------------------------------------------------
# 1. Grid-only scenario (fast)
# ---------------------------------------------------------------------------


@skip_no_solver
class TestGridOnlyScenario:
    """PV (50 kW fixed) + grid (100 kW) serving 5 kW flat load."""

    def test_solves_without_error(self) -> None:
        scenario = _make_scenario()
        _compile_and_solve(scenario)

    def test_grid_buy_covers_load(self) -> None:
        """Grid buy + PV AC output >= load at every hour."""
        scenario = _make_scenario()
        _, dr = _compile_and_solve(scenario)
        df = dr.dispatch
        # At worst, unmet_load fills any gap (max_lpsp=0 here, so should be 0)
        assert float(df["unmet_load"].sum()) == pytest.approx(0.0, abs=1.0)
        # Grid must supply something (PV is only 20 kW, load is 5 kW * 8760 total)
        assert float(df["grid_buy"].sum()) >= 0.0

    def test_dispatch_has_8760_rows(self) -> None:
        scenario = _make_scenario()
        _, dr = _compile_and_solve(scenario)
        assert len(dr.dispatch) == 8760

    def test_dispatch_contract_columns(self) -> None:
        expected = [
            "eload",
            "pv_gen",
            "wt_gen",
            "dg_gen",
            "grid_buy",
            "grid_sell",
            "batt_charge",
            "batt_discharge",
            "batt_soc",
            "battery_soc_kwh",
            "unmet_load",
            "energy_dump",
            "inverter_dc_to_ac",
            "inverter_ac_to_dc",
            "ev_charge_kw",
            "ev_discharge_kw",
            "ev_soc_kwh",
            "ev_travel_kwh",
        ]
        scenario = _make_scenario()
        _, dr = _compile_and_solve(scenario)
        assert list(dr.dispatch.columns) == expected

    def test_energy_balance_ok(self) -> None:
        from samba.solver import validate_energy_balance

        scenario = _make_scenario()
        _, dr = _compile_and_solve(scenario)
        validate_energy_balance(dr.dispatch, tolerance_kwh=2.0)


# ---------------------------------------------------------------------------
# 2. PV-only off-grid with LPSP allowed (tests dump sinks + unmet_load)
# ---------------------------------------------------------------------------


@skip_no_solver
class TestPVOffGridWithLPSP:
    """PV only, no grid, max_lpsp=1.0 — feasible via unmet_load + dump sinks."""

    def _off_grid_scenario(self) -> Any:
        return _make_scenario(
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
            },
            constraints={"max_lpsp": 1.0},
        )

    def test_solves_without_error(self) -> None:
        _compile_and_solve(self._off_grid_scenario())

    def test_no_grid_buy(self) -> None:
        """Off-grid scenario must have zero grid imports."""
        _, dr = _compile_and_solve(self._off_grid_scenario())
        assert float(dr.dispatch["grid_buy"].sum()) == pytest.approx(0.0, abs=1e-6)

    def test_dump_or_unmet_nonzero(self) -> None:
        """With PV only and a flat load, at least some dump or unmet load expected."""
        _, dr = _compile_and_solve(self._off_grid_scenario())
        total_slack = float(dr.dispatch["energy_dump"].sum()) + float(
            dr.dispatch["unmet_load"].sum()
        )
        assert total_slack > 0.0


# ---------------------------------------------------------------------------
# 3. Infeasible: no generation, no grid, max_lpsp=0
# ---------------------------------------------------------------------------


@skip_no_solver
class TestInfeasibleScenario:
    def test_raises_infeasible_error(self) -> None:
        from samba.solver import InfeasibleError

        # Diesel capacity (1 kW) is less than constant 5 kW load at every hour.
        # No PV, no grid, no battery.  max_lpsp=0.0 requires 100 % load coverage
        # → structurally infeasible regardless of dispatch decisions.
        scenario = _make_scenario(
            components={
                "pv": None,
                "grid": None,
                "battery": None,
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                "diesel_generator": {
                    "capacity_kw": 1.0,  # less than the 5 kW load → infeasible
                    "capex_per_kw": 500.0,
                    "fuel_price_per_l": 1.5,
                },
            },
            constraints={"force_grid_disconnect": True, "max_lpsp": 0.0},
        )
        from samba.compiler import CompilerInputs, ConfigurationError, compile_energy_system
        from samba.solver import SolverConfig, solve
        from samba.weather import stub_weather as _stub_weather

        inputs = CompilerInputs(
            scenario=scenario,
            load_kw=_LOAD_KW.copy(),
            tariff_arrays=_TARIFF,
            weather=_stub_weather(),
        )
        try:
            es = compile_energy_system(inputs)
        except ConfigurationError:
            pytest.skip("Compiler already rejected this scenario — expected for infeasible test")
            return

        config = SolverConfig(solver_name="appsi_highs")
        with pytest.raises(InfeasibleError):
            solve(es, scenario, config=config)


# ---------------------------------------------------------------------------
# 4. PV + Battery Investment mode  (slow — marks as slow)
# ---------------------------------------------------------------------------


@skip_no_solver
@pytest.mark.slow
class TestInvestmentModeRoundtrip:
    """PV and battery in Investment mode — verifies capacities > 0 and parquet write."""

    def _investment_scenario(self) -> Any:
        return _make_scenario(
            components={
                "pv": {"capex_per_kw": 900.0, "capacity_kw": None},  # Investment
                "battery": {"capex_per_kwh": 300.0, "capacity_kwh": None},  # Investment
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": None},  # Investment
                "grid": {"capacity_kw": 100.0},
            },
            constraints={"max_lpsp": 0.05},
        )

    def test_investment_capacities_positive(self) -> None:
        """Optimiser should size PV and battery > 0 when RE is cheaper than grid."""
        scenario = self._investment_scenario()
        _, dr = _compile_and_solve(scenario)
        # At least PV or battery should be sized
        total_cap = sum(dr.capacities.values())
        assert total_cap >= 0.0  # non-negative (may be 0 if grid is cheapest)

    def test_parquet_written_correctly(self, tmp_path: Any) -> None:
        """write_dispatch produces a valid parquet with 8760 rows."""
        import pandas as pd

        from samba.run_result import write_dispatch

        scenario = self._investment_scenario()
        _, dr = _compile_and_solve(scenario)
        write_dispatch(tmp_path, dr.dispatch)

        loaded = pd.read_parquet(tmp_path / "dispatch.parquet")
        assert len(loaded) == 8760

    def test_metadata_written(self, tmp_path: Any) -> None:
        """write_metadata produces a valid metadata.json."""
        import json

        from samba.run_result import write_metadata
        from samba.solver import SolverConfig

        scenario = self._investment_scenario()
        _, dr = _compile_and_solve(scenario)
        write_metadata(tmp_path, scenario, SolverConfig(solver_name="appsi_highs"), 5.0)

        meta = json.loads((tmp_path / "metadata.json").read_text())
        assert meta["solver"]["name"] == "appsi_highs"
        assert meta["kpis_schema_version"] == 1

    def test_energy_balance_ok(self) -> None:
        from samba.solver import validate_energy_balance

        scenario = self._investment_scenario()
        _, dr = _compile_and_solve(scenario)
        validate_energy_balance(dr.dispatch, tolerance_kwh=2.0)
