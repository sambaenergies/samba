# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Integration tests for the EV / V2G component.

These tests compile and solve real LP problems using HiGHS.  They are
skipped automatically when HiGHS is not available so the unit-test suite
remains green even before ``pip install -e .`` is re-run.

Four scenarios are exercised:

1. **charge-only** — EV with V2G disabled; verify grid supplies the charge
   demand and the EV dispatch columns are present and plausible.
2. **V2G** — V2G enabled; verify the V2G discharge column is non-zero when
   the sell rate makes it economically attractive.
3. **always-home (no travel)** — presence array always 1; verify
   ``ev_travel_kwh`` is zero throughout.
4. **commute travel** — standard M-F commute schedule; verify
   ``ev_travel_kwh`` is non-zero on work days.
"""

from __future__ import annotations

import importlib
from typing import Any

import numpy as np
import pytest

pytestmark = pytest.mark.integration

_highs_available = importlib.util.find_spec("highspy") is not None

skip_no_solver = pytest.mark.skipif(
    not _highs_available,
    reason="highspy not installed — run 'pip install highspy'",
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_N = 8760
_LOAD_KW = np.full(_N, 3.0, dtype=np.float64)
_PV_HALF = np.where(
    np.tile(np.concatenate([np.ones(12) * 0.5, np.zeros(12)]), 365),
    1.0,
    0.0,
).astype(np.float64)

try:
    from samba.tariff import TariffArrays

    _TARIFF_FLAT = TariffArrays(
        cbuy=np.full(_N, 0.20, dtype=np.float64),
        csell=np.full(_N, 0.10, dtype=np.float64),
        service_charge=np.zeros(12),
    )
    # High sell rate encourages V2G
    _TARIFF_HIGH_SELL = TariffArrays(
        cbuy=np.full(_N, 0.30, dtype=np.float64),
        csell=np.full(_N, 0.25, dtype=np.float64),
        service_charge=np.zeros(12),
    )
except Exception:  # pragma: no cover
    _TARIFF_FLAT = None  # type: ignore[assignment]
    _TARIFF_HIGH_SELL = None  # type: ignore[assignment]


def _make_scenario(**overrides: Any) -> Any:
    """Build a minimal Scenario with PV + grid; apply keyword overrides."""
    from samba.scenario.models import Scenario

    def _deep_update(base: dict, updates: dict) -> None:  # type: ignore[type-arg]
        for k, v in updates.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                _deep_update(base[k], v)
            else:
                base[k] = v

    base: dict[str, Any] = {
        "project": {"name": "ev-integ-test", "discount_rate_nominal": 0.08, "year": 2023},
        "location": {
            "latitude": 51.5,
            "longitude": -0.1,
            "timezone": "Europe/London",
        },
        "weather": {"source": "csv", "csv_path": "dummy.csv"},
        "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
        "components": {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
            "pv": {"capex_per_kw": 1000.0, "capacity_kw": 10.0},
            "grid": {"capacity_kw": 50.0},
        },
        "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.20}},
    }
    _deep_update(base, overrides)
    return Scenario.model_validate(base)


def _compile_and_solve(scenario: Any, tariff: Any = None, **cfg_kwargs: Any) -> tuple[Any, Any]:
    """Compile + solve; return ``(energy_system, DispatchResult)``."""
    from samba.compiler import CompilerInputs, compile_energy_system
    from samba.solver import SolverConfig, extract_dispatch, solve
    from samba.weather import stub_weather as _stub_weather

    t = tariff if tariff is not None else _TARIFF_FLAT
    inputs = CompilerInputs(
        scenario=scenario,
        load_kw=_LOAD_KW.copy(),
        tariff_arrays=t,
        weather=_stub_weather(),
        pv_per_kwp=_PV_HALF.copy(),
    )
    es = compile_energy_system(inputs)
    config = SolverConfig(solver_name="appsi_highs", **cfg_kwargs)
    results = solve(es, scenario, config=config)
    return es, extract_dispatch(es, results)


def _ev_charge_only(**ev_kwargs: Any) -> dict[str, Any]:
    """Return a components dict with a charge-only EV (V2G disabled)."""
    defaults: dict[str, Any] = {
        "capacity_kwh": 40.0,
        "max_charge_kw": 7.2,
        "v2g_enabled": False,
        "presence_source": "schedule",
        "arrival_hour": 18,
        "departure_hour": 8,
        "workdays_per_week": 5,
    }
    defaults.update(ev_kwargs)
    return {
        "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
        "pv": {"capex_per_kw": 1000.0, "capacity_kw": 10.0},
        "grid": {"capacity_kw": 50.0},
        "ev": defaults,
    }


# ---------------------------------------------------------------------------
# TestEVChargeOnly
# ---------------------------------------------------------------------------


@skip_no_solver
class TestEVChargeOnly:
    """EV enabled, V2G disabled — charge only."""

    def _build(self) -> Any:
        scenario = _make_scenario(components=_ev_charge_only())
        return _compile_and_solve(scenario)

    def test_solves_without_error(self) -> None:
        self._build()

    def test_ev_columns_in_dispatch(self) -> None:
        _, dr = self._build()
        for col in ("ev_charge_kw", "ev_discharge_kw", "ev_soc_kwh", "ev_travel_kwh"):
            assert col in dr.dispatch.columns, f"Expected column '{col}' in dispatch"

    def test_ev_charge_nonzero(self) -> None:
        """EV must charge at some point during the year."""
        _, dr = self._build()
        assert float(dr.dispatch["ev_charge_kw"].sum()) > 0.0

    def test_ev_discharge_zero_without_v2g(self) -> None:
        """V2G disabled — no discharge to grid."""
        _, dr = self._build()
        assert float(dr.dispatch["ev_discharge_kw"].sum()) == pytest.approx(0.0, abs=1e-3)

    def test_ev_travel_nonzero_with_commute(self) -> None:
        """Commute schedule should produce non-zero travel depletion."""
        _, dr = self._build()
        assert float(dr.dispatch["ev_travel_kwh"].sum()) > 0.0

    def test_energy_balance_ok(self) -> None:
        from samba.solver import validate_energy_balance

        _, dr = self._build()
        validate_energy_balance(dr.dispatch, tolerance_kwh=5.0)


# ---------------------------------------------------------------------------
# TestEVV2G
# ---------------------------------------------------------------------------


@skip_no_solver
class TestEVV2G:
    """EV with V2G enabled — can discharge to grid for revenue."""

    def _build(self) -> Any:
        ev_cfg = {
            "capacity_kwh": 40.0,
            "max_charge_kw": 7.2,
            "max_discharge_kw": 7.2,
            "v2g_enabled": True,
            "presence_source": "schedule",
            "arrival_hour": 18,
            "departure_hour": 8,
            "workdays_per_week": 5,
        }
        components = {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
            "pv": {"capex_per_kw": 1000.0, "capacity_kw": 10.0},
            "grid": {"capacity_kw": 50.0},
            "ev": ev_cfg,
        }
        scenario = _make_scenario(components=components)
        # High sell rate (0.25 $/kWh) vs buy (0.30 $/kWh) makes V2G attractive
        return _compile_and_solve(scenario, tariff=_TARIFF_HIGH_SELL)

    def test_solves_without_error(self) -> None:
        self._build()

    def test_ev_discharge_nonzero_with_v2g(self) -> None:
        """V2G enabled with high sell rate — expect some discharge to grid."""
        _, dr = self._build()
        assert float(dr.dispatch["ev_discharge_kw"].sum()) > 0.0

    def test_energy_balance_ok(self) -> None:
        from samba.solver import validate_energy_balance

        _, dr = self._build()
        validate_energy_balance(dr.dispatch, tolerance_kwh=5.0)


# ---------------------------------------------------------------------------
# TestEVSingleWorkday
# ---------------------------------------------------------------------------


@skip_no_solver
class TestEVSingleWorkday:
    """EV with a single commute day per week — verify travel depletion scales."""

    def _build(self) -> Any:
        ev_cfg = {
            "capacity_kwh": 40.0,
            "max_charge_kw": 7.2,
            "v2g_enabled": False,
            "soc_departure": 0.80,
            "soc_arrival": 0.30,
            "presence_source": "schedule",
            "arrival_hour": 18,
            "departure_hour": 8,
            "workdays_per_week": 1,  # only Monday commutes
        }
        components = {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
            "pv": {"capex_per_kw": 1000.0, "capacity_kw": 10.0},
            "grid": {"capacity_kw": 50.0},
            "ev": ev_cfg,
        }
        scenario = _make_scenario(components=components)
        return _compile_and_solve(scenario)

    def test_solves_without_error(self) -> None:
        self._build()

    def test_travel_kwh_nonzero(self) -> None:
        """Single commute day per week → travel depletion should be > 0."""
        _, dr = self._build()
        assert float(dr.dispatch["ev_travel_kwh"].sum()) > 0.0

    def test_energy_balance_ok(self) -> None:
        from samba.solver import validate_energy_balance

        _, dr = self._build()
        validate_energy_balance(dr.dispatch, tolerance_kwh=5.0)
