"""Integration tests for DG unit commitment (MILP).

These tests invoke the real HiGHS MILP solver and are skipped if HiGHS is
not available.  The fast MILP tests use a 168-hour (1-week) energy system
built directly through oemof-solph; the full-year tests exercise the real
8760-hour :func:`~samba.compiler.compile_energy_system` pipeline.

Fast MILP tests (168 h horizon, each < 60 s):
  TestMILPMinUptime    — on-segment length ≥ min_up_hours
  TestMILPMinDowntime  — off-gap length ≥ min_down_hours
  TestMILPStartupCost  — fewer start events reduces vs zero startup_cost

Regression (8760 h, LP, fast):
  TestLPRegression     — v1-equivalent LP (no NonConvex) still solves correctly

Full-year MILP (8760 h, through the compiler pipeline) — audit item C1:
  TestMILPFullYear     — min_up/min_down honoured and startup cost reduces
                         starts at the full-year horizon a real run uses.

All integration tests are marked ``integration``.
MILP 168-h tests are also marked ``milp`` (but NOT ``slow``); the full-year
MILP tests are marked ``milp`` and ``slow``.
"""

from __future__ import annotations

import importlib
from typing import Any

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.integration

_highs_available = importlib.util.find_spec("highspy") is not None

skip_no_solver = pytest.mark.skipif(
    not _highs_available,
    reason="highspy not installed — run 'pip install highspy' or 'pip install -e .'",
)

# ---------------------------------------------------------------------------
# Constants for 168-hour test horizon
# ---------------------------------------------------------------------------

_N = 168  # 1 week of hourly timesteps
_N_FULL = 8760  # full year LP regression

# Flat 8 kW load for the 168-h tests
_LOAD_KW_168 = np.full(_N, 8.0, dtype=np.float64)

# DG capacity slightly above load so it can always serve alone
_DG_KW = 10.0

# ---------------------------------------------------------------------------
# Helper: build a minimal 168-h oemof energy system with DG + grid
# ---------------------------------------------------------------------------


def _make_168h_es_with_dg(
    min_up_hours: int = 0,
    min_down_hours: int = 0,
    startup_cost: float = 0.0,
    min_load_fraction: float = 0.0,
) -> Any:
    """Return a 168-h oemof EnergySystem: grid + DG serving a flat load.

    The grid is always available at a high cost (0.50 $/kWh) so the solver
    prefers the cheaper DG (0.20 $/kWh) whenever the unit-commitment
    constraints allow it.  This creates interesting on/off cycling that lets
    the min_up/min_down constraints be tested.

    Parameters
    ----------
    min_up_hours, min_down_hours, startup_cost, min_load_fraction:
        DG unit-commitment parameters forwarded to the NonConvex object.

    Returns
    -------
    solph.EnergySystem
        Not yet solved; call ``solph.Model(es)`` and ``model.solve()`` externally.
    """
    import oemof.solph as solph
    from oemof.solph import NonConvex  # noqa: F401 — used conditionally

    ts = pd.date_range("2024-01-01", periods=_N, freq="h")
    es = solph.EnergySystem(timeindex=ts, infer_last_interval=False)

    ac_bus = solph.Bus(label="ac_bus")

    # Load sink — normalize fix to 0-1 range (oemof convention)
    load_max = float(_LOAD_KW_168.max())
    load_norm = _LOAD_KW_168 / load_max
    load_sink = solph.components.Sink(
        label="load",
        inputs={ac_bus: solph.Flow(fix=load_norm, nominal_capacity=load_max)},
    )

    # Grid (always available but expensive)
    grid_src = solph.components.Source(
        label="grid",
        outputs={ac_bus: solph.Flow(variable_costs=0.50, nominal_capacity=50.0)},
    )

    # DG: cheaper but subject to unit-commitment constraints
    milp_mode = (
        min_up_hours > 0 or min_down_hours > 0 or startup_cost > 0.0 or min_load_fraction > 0.0
    )

    if milp_mode:
        nc = NonConvex(
            minimum_uptime=min_up_hours,
            minimum_downtime=min_down_hours,
            startup_costs=startup_cost,
        )
        dg_flow = solph.Flow(
            nominal_capacity=_DG_KW,
            variable_costs=0.20,
            minimum=min_load_fraction,
            nonconvex=nc,
        )
    else:
        dg_flow = solph.Flow(
            nominal_capacity=_DG_KW,
            variable_costs=0.20,
        )

    # Fuel bus → DG converter topology (mirrors DieselBuilder)
    fuel_bus = solph.Bus(label="fuel_bus")
    fuel_src = solph.components.Source(
        label="fuel_source",
        outputs={fuel_bus: solph.Flow(variable_costs=0.0)},
    )
    dg_conv = solph.components.Converter(
        label="dg",
        inputs={fuel_bus: solph.Flow()},
        outputs={ac_bus: dg_flow},
        conversion_factors={fuel_bus: 1.0, ac_bus: 1.0},
    )

    es.add(ac_bus, fuel_bus, load_sink, grid_src, fuel_src, dg_conv)
    return es


def _solve_168h(es: Any) -> Any:
    """Build a solph.Model, solve it with HiGHS, and return the model."""
    import oemof.solph as solph
    import pyomo.environ as pyo  # noqa: F401 — registers APPSI

    model = solph.Model(es)

    # APPSI compat fix (same as runner.py)
    for _attr in ("dual", "rc"):
        if model.__dict__.get(_attr) is None:
            model.__dict__.pop(_attr, None)

    opt = pyo.SolverFactory("appsi_highs")
    opt.options["time_limit"] = 120.0
    opt.options["mip_rel_gap"] = 0.01
    solver_results = opt.solve(model, tee=False)
    model.solver_results = solver_results
    model.es.results = solver_results
    return model


def _dg_dispatch_168(model: Any) -> np.ndarray:
    """Return 168-element array of DG output (kW) from the solved model."""
    import oemof.solph as solph

    results = solph.Results(model)
    flows = results.get("flow")

    for (from_node, to_node), series in flows.items():
        if (
            hasattr(from_node, "label")
            and from_node.label == "dg"
            and hasattr(to_node, "label")
            and to_node.label == "ac_bus"
        ):
            return np.asarray(series.values.flatten(), dtype=float)

    raise AssertionError("Could not find DG → AC flow in results")


def _run_segments(arr: np.ndarray, on: bool = True, threshold: float = 0.01) -> list[int]:
    """Return list of consecutive segment lengths.

    When *on=True*, counts segments where ``arr > threshold``.
    When *on=False*, counts segments where ``arr <= threshold`` (off-gaps).
    """
    active = (arr > threshold) if on else (arr <= threshold)
    lengths: list[int] = []
    count = 0
    for val in active:
        if val:
            count += 1
        else:
            if count > 0:
                lengths.append(count)
            count = 0
    if count > 0:
        lengths.append(count)
    return lengths


# ---------------------------------------------------------------------------
# Helpers for full-year LP regression
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(42)
_LOAD_KW_FULL = np.full(_N_FULL, 5.0, dtype=np.float64)

try:
    from samba.tariff import TariffArrays as _TariffArrays

    _TARIFF_FULL = _TariffArrays(
        cbuy=np.full(_N_FULL, 0.15, dtype=np.float64),
        csell=np.full(_N_FULL, 0.06, dtype=np.float64),
        service_charge=np.zeros(12),
    )
except Exception:  # pragma: no cover
    _TARIFF_FULL = None  # type: ignore[assignment]


def _make_lp_scenario(**overrides: Any) -> Any:
    """Minimal Scenario with DG (LP mode: all UC fields = 0)."""
    from samba.scenario.models import Scenario

    def _deep(base: dict, up: dict) -> None:  # type: ignore[type-arg]
        for k, v in up.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                _deep(base[k], v)
            else:
                base[k] = v

    base: dict[str, Any] = {
        "project": {"name": "lp-dg-regress", "discount_rate_nominal": 0.08},
        "location": {
            "latitude": 37.77,
            "longitude": -122.42,
            "timezone": "America/Los_Angeles",
        },
        "weather": {"source": "csv", "csv_path": "dummy.csv"},
        "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
        "components": {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
            "grid": {"capacity_kw": 100.0},
            "diesel_generator": {
                "capacity_kw": 10.0,
                "capex_per_kw": 400.0,
                "fuel_price_per_l": 1.20,
                # LP mode: no UC fields set (defaults 0)
            },
        },
        "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.15}},
    }
    _deep(base, overrides)
    return Scenario.model_validate(base)


def _compile_and_solve_lp(scenario: Any) -> Any:
    from samba.compiler import CompilerInputs, compile_energy_system
    from samba.solver import SolverConfig, extract_dispatch, solve
    from samba.weather import stub_weather as _stub_weather

    inputs = CompilerInputs(
        scenario=scenario,
        load_kw=_LOAD_KW_FULL.copy(),
        tariff_arrays=_TARIFF_FULL,
        weather=_stub_weather(),
    )
    es = compile_energy_system(inputs)
    config = SolverConfig(solver_name="appsi_highs")
    results = solve(es, scenario, config=config)
    return extract_dispatch(es, results)


# ---------------------------------------------------------------------------
# TestMILPMinUptime
# ---------------------------------------------------------------------------


@skip_no_solver
@pytest.mark.milp
class TestMILPMinUptime:
    """min_up_hours=4 → no DG on-segment shorter than 4 consecutive hours."""

    def test_lp_baseline_solves(self) -> None:
        """LP baseline (no UC) completes without error."""
        es = _make_168h_es_with_dg()
        model = _solve_168h(es)
        tc = str(model.solver_results.Solver.Termination_condition).lower()
        assert "optimal" in tc

    def test_milp_min_up_4_solves(self) -> None:
        es = _make_168h_es_with_dg(min_up_hours=4)
        model = _solve_168h(es)
        tc = str(model.solver_results.Solver.Termination_condition).lower()
        assert "optimal" in tc

    def test_milp_min_up_4_no_short_on_segments(self) -> None:
        """Every DG on-segment must be ≥ 4 hours long."""
        es = _make_168h_es_with_dg(min_up_hours=4)
        model = _solve_168h(es)
        dg_out = _dg_dispatch_168(model)
        on_segs = _run_segments(dg_out, on=True, threshold=0.01)
        for seg_len in on_segs:
            assert seg_len >= 4, (
                f"DG on-segment of length {seg_len} found, expected >= 4 (min_up_hours=4). "
                f"All on-segment lengths: {on_segs}"
            )

    def test_milp_energy_balance(self) -> None:
        """Total DG output + grid buy >= total load (within 1% tolerance)."""
        es = _make_168h_es_with_dg(min_up_hours=4)
        model = _solve_168h(es)
        # Get grid output
        import oemof.solph as solph

        results = solph.Results(model)
        flows = results.get("flow")
        grid_out: np.ndarray | None = None
        dg_out: np.ndarray | None = None
        for (fn, _tn), series in flows.items():
            if hasattr(fn, "label") and fn.label == "grid":
                grid_out = np.asarray(series.values.flatten(), dtype=float)
            if hasattr(fn, "label") and fn.label == "dg":
                dg_out = np.asarray(series.values.flatten(), dtype=float)

        supply = (grid_out if grid_out is not None else 0) + (dg_out if dg_out is not None else 0)
        assert float(np.sum(supply)) == pytest.approx(float(np.sum(_LOAD_KW_168)), rel=0.02)


# ---------------------------------------------------------------------------
# TestMILPMinDowntime
# ---------------------------------------------------------------------------


@skip_no_solver
@pytest.mark.milp
class TestMILPMinDowntime:
    """min_down_hours=4 → no DG off-gap shorter than 4 consecutive hours."""

    def test_milp_min_down_4_solves(self) -> None:
        es = _make_168h_es_with_dg(min_down_hours=4)
        model = _solve_168h(es)
        tc = str(model.solver_results.Solver.Termination_condition).lower()
        assert "optimal" in tc

    def test_milp_min_down_4_no_short_off_gaps(self) -> None:
        """Every DG off-gap must be ≥ 4 hours long (if the DG ever turns off)."""
        es = _make_168h_es_with_dg(min_down_hours=4)
        model = _solve_168h(es)
        dg_out = _dg_dispatch_168(model)
        off_segs = _run_segments(dg_out, on=False, threshold=0.01)
        for seg_len in off_segs:
            assert seg_len >= 4, (
                f"DG off-gap of length {seg_len} found, expected >= 4 (min_down_hours=4). "
                f"All off-segment lengths: {off_segs}"
            )


# ---------------------------------------------------------------------------
# TestMILPStartupCost
# ---------------------------------------------------------------------------


@skip_no_solver
@pytest.mark.milp
class TestMILPStartupCost:
    """startup_cost > 0 → fewer start events vs zero startup_cost."""

    def _count_starts(self, dg_out: np.ndarray, threshold: float = 0.01) -> int:
        """Count the number of transitions from off to on."""
        on = dg_out > threshold
        return int(np.sum(~on[:-1] & on[1:]))

    def test_startup_cost_50_solves(self) -> None:
        es = _make_168h_es_with_dg(startup_cost=50.0)
        model = _solve_168h(es)
        tc = str(model.solver_results.Solver.Termination_condition).lower()
        assert "optimal" in tc

    def test_startup_cost_reduces_cycling(self) -> None:
        """A high startup cost should reduce DG cycling vs zero startup cost.

        We run both variants and assert starts(high_cost) <= starts(zero_cost).
        """
        es_cheap = _make_168h_es_with_dg(startup_cost=0.0, min_up_hours=1)
        model_cheap = _solve_168h(es_cheap)
        dg_cheap = _dg_dispatch_168(model_cheap)
        starts_cheap = self._count_starts(dg_cheap)

        es_costly = _make_168h_es_with_dg(startup_cost=200.0)
        model_costly = _solve_168h(es_costly)
        dg_costly = _dg_dispatch_168(model_costly)
        starts_costly = self._count_starts(dg_costly)

        assert starts_costly <= starts_cheap, (
            f"Expected fewer starts with startup_cost=200 ({starts_costly}) "
            f"vs startup_cost=0 ({starts_cheap})."
        )


# ---------------------------------------------------------------------------
# TestLPRegression — full 8760-hour LP (no NonConvex), no solver regression
# ---------------------------------------------------------------------------


@skip_no_solver
class TestLPRegression:
    """DG with all UC fields at defaults (0) solves as pure LP, no regression."""

    def test_lp_dg_solves_without_error(self) -> None:
        scenario = _make_lp_scenario()
        _compile_and_solve_lp(scenario)

    def test_lp_dg_dispatch_has_8760_rows(self) -> None:
        scenario = _make_lp_scenario()
        dr = _compile_and_solve_lp(scenario)
        assert len(dr.dispatch) == 8760

    def test_lp_dg_zero_unmet_load(self) -> None:
        """Grid + DG always satisfy flat 5 kW load."""
        scenario = _make_lp_scenario()
        dr = _compile_and_solve_lp(scenario)
        assert float(dr.dispatch["unmet_load"].sum()) == pytest.approx(0.0, abs=1.0)

    def test_lp_dg_energy_balance(self) -> None:
        from samba.solver import validate_energy_balance

        scenario = _make_lp_scenario()
        dr = _compile_and_solve_lp(scenario)
        validate_energy_balance(dr.dispatch)  # raises EnergyBalanceError on failure


# ---------------------------------------------------------------------------
# TestMILPFullYear — full 8760-hour MILP unit commitment through the real
# compiler pipeline.
#
# Closes audit item C1: prior to this, MILP unit commitment was only ever
# exercised at the 168-h horizon (TestMILP* above), so the full-year MILP path
# a real ``samba run`` takes was untested.  oemof-solph 0.6.4 solves the
# 8760-h MILP correctly; these tests lock that in and guard against regression.
#
# Counting note: these scenarios set ``min_load_fraction = 0.3`` so the DG flow
# is zero exactly when the unit is committed off.  This makes flow-threshold
# segment counting equal to the true on/off (status) schedule — without a
# minimum, a committed unit can idle at zero output and flow dips would
# over-count starts.
# ---------------------------------------------------------------------------


def _cycling_cbuy(expensive_hours: int, cheap_hours: int) -> np.ndarray:
    """Return an 8760-element buy-rate array alternating expensive/cheap blocks.

    Cheap (0.05 $/kWh) undercuts the DG fuel cost so the grid serves the load;
    expensive (0.50 $/kWh) makes the DG the cheaper source.  This drives on/off
    cycling whose period the unit-commitment constraints must reshape.
    """
    period = expensive_hours + cheap_hours
    block = np.concatenate([np.full(expensive_hours, 0.50), np.full(cheap_hours, 0.05)])
    reps = _N_FULL // period + 1
    return np.tile(block, reps)[:_N_FULL].astype(np.float64)


def _make_uc_scenario(**dg_overrides: Any) -> Any:
    """Full-year Scenario with a DG in MILP mode (UC fields + min_load_fraction)."""
    dg: dict[str, Any] = {
        "capacity_kw": 10.0,
        "capex_per_kw": 400.0,
        "fuel_price_per_l": 1.20,
        "min_load_fraction": 0.3,
    }
    dg.update(dg_overrides)
    return _make_lp_scenario(components={"diesel_generator": dg})


def _compile_and_solve_uc(scenario: Any, cbuy: np.ndarray) -> Any:
    from samba.compiler import CompilerInputs, compile_energy_system
    from samba.solver import SolverConfig, extract_dispatch, solve
    from samba.tariff import TariffArrays
    from samba.weather import stub_weather as _stub_weather

    tariff = TariffArrays(
        cbuy=cbuy,
        csell=np.zeros(_N_FULL, dtype=np.float64),
        service_charge=np.zeros(12),
    )
    inputs = CompilerInputs(
        scenario=scenario,
        load_kw=np.full(_N_FULL, 8.0, dtype=np.float64),
        tariff_arrays=tariff,
        weather=_stub_weather(),
    )
    es = compile_energy_system(inputs)
    results = solve(es, scenario, config=SolverConfig(solver_name="appsi_highs"))
    return extract_dispatch(es, results)


def _interior_runs(dg_kw: np.ndarray, on: bool, threshold: float = 0.01) -> list[int]:
    """Return lengths of fully-interior on/off runs.

    Runs that touch hour 0 or the final hour are excluded: a finite horizon
    clips them, and minimum up/down constraints do not apply to a segment with
    no history before t=0 or one cut short at t=N-1.
    """
    active = (dg_kw > threshold) if on else (dg_kw <= threshold)
    runs: list[int] = []
    count = 0
    started_at_boundary = False
    for i, val in enumerate(active):
        if val:
            if count == 0:
                started_at_boundary = i == 0
            count += 1
        else:
            if count > 0 and not started_at_boundary:  # bounded by an off-hour on both sides
                runs.append(count)
            count = 0
    # A run still open here reaches the final hour -> boundary-clipped, excluded.
    return runs


def _count_full_year_starts(dg_kw: np.ndarray, threshold: float = 0.01) -> int:
    on = dg_kw > threshold
    return int(np.sum(~on[:-1] & on[1:]))


@skip_no_solver
@pytest.mark.milp
@pytest.mark.slow
class TestMILPFullYear:
    """Unit commitment is correct over the full 8760-h horizon (audit C1)."""

    def test_full_year_milp_solves_with_8760_rows(self) -> None:
        """A full-year MILP scenario solves and yields 8760 dispatch rows.

        This is the path a real ``samba run`` with ``min_up_hours`` takes;
        the audit flagged it as silently infeasible on an older oemof-solph.
        """
        scenario = _make_uc_scenario(min_up_hours=6)
        dr = _compile_and_solve_uc(scenario, _cycling_cbuy(expensive_hours=4, cheap_hours=8))
        assert len(dr.dispatch) == 8760
        assert float(dr.dispatch["unmet_load"].sum()) == pytest.approx(0.0, abs=1.0)
        # The DG must actually run (otherwise the constraint test below is vacuous).
        assert float(dr.dispatch["dg_gen"].sum()) > 0.0

    def test_full_year_min_up_honored(self) -> None:
        """Every DG on-segment is at least ``min_up_hours`` long over 8760 h.

        Natural on-window is 4 h (the expensive block); min_up_hours=6 forces
        every on-segment to stretch to >= 6 h.
        """
        scenario = _make_uc_scenario(min_up_hours=6)
        dr = _compile_and_solve_uc(scenario, _cycling_cbuy(expensive_hours=4, cheap_hours=8))
        dg = dr.dispatch["dg_gen"].to_numpy()
        on_segs = _interior_runs(dg, on=True)
        assert on_segs, "DG never turned on; cannot validate min_up_hours"
        assert min(on_segs) >= 6, f"shortest on-segment {min(on_segs)} < min_up_hours=6"

    def test_full_year_min_down_honored(self) -> None:
        """Every DG off-gap is at least ``min_down_hours`` long over 8760 h.

        Natural off-window is 5 h (the cheap block); min_down_hours=6 forces
        every off-gap to stretch to >= 6 h (only 1 h past the economical window,
        so the constraint binds without making cycling itself unprofitable).
        """
        scenario = _make_uc_scenario(min_down_hours=6)
        dr = _compile_and_solve_uc(scenario, _cycling_cbuy(expensive_hours=7, cheap_hours=5))
        dg = dr.dispatch["dg_gen"].to_numpy()
        off_segs = _interior_runs(dg, on=False)
        assert off_segs, "DG never cycled off; cannot validate min_down_hours"
        assert min(off_segs) >= 6, f"shortest off-gap {min(off_segs)} < min_down_hours=6"

    def test_full_year_startup_cost_reduces_starts(self) -> None:
        """A high startup cost reduces real engine starts over the full year.

        With a daily 12/12 price cycle and no startup cost the DG starts ~once
        per day; a large startup cost makes it cheaper to stay committed
        (idling at min load), cutting the number of starts.
        """
        cbuy = _cycling_cbuy(expensive_hours=12, cheap_hours=12)

        dr_free = _compile_and_solve_uc(_make_uc_scenario(startup_cost=0.0), cbuy)
        starts_free = _count_full_year_starts(dr_free.dispatch["dg_gen"].to_numpy())

        dr_costly = _compile_and_solve_uc(_make_uc_scenario(startup_cost=2000.0), cbuy)
        starts_costly = _count_full_year_starts(dr_costly.dispatch["dg_gen"].to_numpy())

        assert starts_free > 100, (
            f"expected frequent cycling without startup cost; got {starts_free} starts"
        )
        assert starts_costly < starts_free, (
            f"startup_cost=2000 did not reduce starts: {starts_costly} vs {starts_free} "
            "(startup costs may be silently dropped at the full-year horizon — audit C1)"
        )
