"""Unit tests for samba.batteries.kibam — compute_kibam_limits and
validate_kibam_dispatch."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from samba.batteries.kibam import (
    KiBaMValidationResult,
    compute_kibam_limits,
    validate_kibam_dispatch,
)
from samba.scenario.models import KiBaMParams

# ---------------------------------------------------------------------------
# Default KiBaM params (typical lead-acid defaults)
# ---------------------------------------------------------------------------

_DEFAULT_KIBAM = KiBaMParams()  # c=0.42, k=0.58, charge_acceptance=0.9


# ---------------------------------------------------------------------------
# compute_kibam_limits
# ---------------------------------------------------------------------------


class TestComputeKiBaMlimits:
    def test_default_params_dch_less_than_1c(self) -> None:
        """Default lead-acid params → discharge C-rate limit < 1C."""
        limits = compute_kibam_limits(_DEFAULT_KIBAM, capacity_kwh=10.0, soc_min=0.2, soc_max=1.0)
        assert limits["c_rate_dch_limit"] < 1.0, "Lead-acid discharge C-rate must be < 1C"

    def test_default_params_ch_less_than_1c(self) -> None:
        """Default lead-acid params → charge C-rate limit < 1C."""
        limits = compute_kibam_limits(_DEFAULT_KIBAM, capacity_kwh=10.0, soc_min=0.2, soc_max=1.0)
        # Lead-acid charge acceptance limits charging to < 1C
        assert limits["c_rate_ch_limit"] < 1.0

    def test_limits_positive(self) -> None:
        """All returned limits must be non-negative."""
        limits = compute_kibam_limits(_DEFAULT_KIBAM, capacity_kwh=20.0, soc_min=0.1, soc_max=0.95)
        assert limits["c_rate_dch_limit"] >= 0.0
        assert limits["c_rate_ch_limit"] >= 0.0
        assert limits["pdch_max_kw"] >= 0.0
        assert limits["pch_max_kw"] >= 0.0

    def test_absolute_and_relative_consistent(self) -> None:
        """c_rate_dch_limit * capacity_kwh == pdch_max_kw."""
        cap = 15.0
        limits = compute_kibam_limits(_DEFAULT_KIBAM, capacity_kwh=cap, soc_min=0.2, soc_max=1.0)
        assert limits["pdch_max_kw"] == pytest.approx(limits["c_rate_dch_limit"] * cap, rel=1e-10)
        assert limits["pch_max_kw"] == pytest.approx(limits["c_rate_ch_limit"] * cap, rel=1e-10)

    def test_c_ratio_1_approaches_idealized(self) -> None:
        """c_ratio=1.0 (all charge available) → discharge limit rises toward higher C-rate."""
        ideal_kibam = KiBaMParams(c_ratio=0.999)  # near 1.0 (forbidden exactly for validator)
        limits_ideal = compute_kibam_limits(
            ideal_kibam, capacity_kwh=10.0, soc_min=0.2, soc_max=1.0
        )
        limits_default = compute_kibam_limits(
            _DEFAULT_KIBAM, capacity_kwh=10.0, soc_min=0.2, soc_max=1.0
        )
        # With more available charge, discharge limit should be higher
        assert limits_ideal["c_rate_dch_limit"] > limits_default["c_rate_dch_limit"]

    def test_c_ratio_validator_rejects_0_and_1(self) -> None:
        with pytest.raises(ValueError, match="c_ratio"):
            KiBaMParams(c_ratio=0.0)
        with pytest.raises(ValueError, match="c_ratio"):
            KiBaMParams(c_ratio=1.0)

    def test_k_rate_validator_rejects_zero(self) -> None:
        with pytest.raises(ValueError, match="k_rate"):
            KiBaMParams(k_rate=0.0)

    def test_larger_capacity_scales_absolute_limits(self) -> None:
        """Doubling capacity should double absolute kW limits."""
        lim10 = compute_kibam_limits(_DEFAULT_KIBAM, capacity_kwh=10.0, soc_min=0.2, soc_max=1.0)
        lim20 = compute_kibam_limits(_DEFAULT_KIBAM, capacity_kwh=20.0, soc_min=0.2, soc_max=1.0)
        assert lim20["pdch_max_kw"] == pytest.approx(lim10["pdch_max_kw"] * 2, rel=1e-10)
        assert lim20["pch_max_kw"] == pytest.approx(lim10["pch_max_kw"] * 2, rel=1e-10)


# ---------------------------------------------------------------------------
# validate_kibam_dispatch
# ---------------------------------------------------------------------------


class TestValidateKiBaMDispatch:
    def _make_zero_dispatch(self, n: int = 8760) -> np.ndarray:
        return np.zeros(n, dtype=np.float64)

    def test_zero_dispatch_feasible(self) -> None:
        result = validate_kibam_dispatch(
            dispatch_kw=self._make_zero_dispatch(),
            capacity_kwh=10.0,
            kibam=_DEFAULT_KIBAM,
            soc_initial=0.5,
        )
        assert result.feasible is True
        assert result.n_violations == 0
        assert result.worst_q1_deficit_kwh == 0.0

    def test_zero_dispatch_q1_plus_q2_equals_initial_energy(self) -> None:
        """With zero power, Q1+Q2 should stay constant (= initial energy)."""
        cap = 10.0
        soc0 = 0.5
        result = validate_kibam_dispatch(
            dispatch_kw=self._make_zero_dispatch(),
            capacity_kwh=cap,
            kibam=_DEFAULT_KIBAM,
            soc_initial=soc0,
        )
        expected_energy = soc0 * cap
        total_energy = result.q1 + result.q2
        # After first timestep, should converge to equilibrium — but total stays ~constant
        assert total_energy == pytest.approx(np.full(8760, expected_energy), abs=1e-6)

    def test_gentle_discharge_feasible(self) -> None:
        """Tiny constant discharge from high SOC → feasible.

        0.0005 kW × 8760 h = 4.38 kWh drawn from a 10 kWh battery starting at
        80% SOC (8 kWh available), well within kinetic limits.
        """
        cap = 10.0
        # 0.00005C rate — total discharge 4.38 kWh from 8 kWh available
        gentle = np.full(8760, 0.0005, dtype=np.float64)
        result = validate_kibam_dispatch(
            dispatch_kw=gentle,
            capacity_kwh=cap,
            kibam=_DEFAULT_KIBAM,
            soc_initial=0.8,
        )
        assert result.feasible is True

    def test_aggressive_discharge_from_low_soc_infeasible(self) -> None:
        """Aggressive full-capacity discharge from near-minimum SOC → infeasible."""
        cap = 10.0
        # Discharge at 1C from SOC=0.25 (very low): Q1 should go negative quickly
        aggressive = np.full(40, cap * 1.0, dtype=np.float64)  # 40 timesteps of 1C
        aggressive = np.concatenate([aggressive, np.zeros(8720)])
        result = validate_kibam_dispatch(
            dispatch_kw=aggressive,
            capacity_kwh=cap,
            kibam=_DEFAULT_KIBAM,
            soc_initial=0.25,  # near the bottom
        )
        assert result.feasible is False
        assert result.n_violations > 0
        assert result.worst_q1_deficit_kwh < 0.0

    def test_result_has_correct_array_shapes(self) -> None:
        result = validate_kibam_dispatch(
            dispatch_kw=np.zeros(8760),
            capacity_kwh=10.0,
            kibam=_DEFAULT_KIBAM,
            soc_initial=0.5,
        )
        assert result.q1.shape == (8760,)
        assert result.q2.shape == (8760,)
        assert result.soc.shape == (8760,)

    def test_returns_kibam_validation_result(self) -> None:
        result = validate_kibam_dispatch(
            dispatch_kw=np.zeros(100),
            capacity_kwh=10.0,
            kibam=_DEFAULT_KIBAM,
            soc_initial=0.5,
        )
        assert isinstance(result, KiBaMValidationResult)

    def test_soc_bounded_for_zero_dispatch(self) -> None:
        """Zero dispatch → SOC stays at initial value."""
        cap = 12.0
        soc0 = 0.6
        result = validate_kibam_dispatch(
            dispatch_kw=np.zeros(8760),
            capacity_kwh=cap,
            kibam=_DEFAULT_KIBAM,
            soc_initial=soc0,
        )
        # SOC should be approximately constant at soc0 (minor floating point drift)
        np.testing.assert_allclose(result.soc, soc0, atol=1e-6)


# ---------------------------------------------------------------------------
# strict_kibam wiring (audit M5)
# ---------------------------------------------------------------------------


class TestStrictKiBaMWiring:
    """``SolverConfig.strict_kibam`` turns post-solve violations into errors."""

    @staticmethod
    def _kibam_scenario() -> object:
        from samba.scenario.models import Scenario

        return Scenario.model_validate(
            {
                "project": {"name": "strict-kibam", "discount_rate_nominal": 0.08},
                "location": {
                    "latitude": 37.0,
                    "longitude": -122.0,
                    "timezone": "America/Los_Angeles",
                },
                "weather": {"source": "csv", "csv_path": "d.csv"},
                "load": {"source": "hourly_csv", "csv_path": "d.csv"},
                "components": {
                    "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
                    "grid": {"capacity_kw": 100.0},
                    "battery": {
                        "capacity_kwh": 10.0,
                        "capex_per_kwh": 300.0,
                        "chemistry": "kibam",
                        "kibam": {},
                    },
                },
                "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.15}},
            }
        )

    @staticmethod
    def _dispatch_df() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "batt_discharge": [1.0, 1.0],
                "batt_charge": [0.0, 0.0],
                "battery_soc_kwh": [5.0, 4.0],
            }
        )

    def _patch_infeasible(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Force the two-tank check to report an infeasible dispatch."""
        import samba.batteries.kibam as kibam_mod

        infeasible = KiBaMValidationResult(
            feasible=False,
            n_violations=3,
            worst_q1_deficit_kwh=-1.25,
            q1=np.zeros(2),
            q2=np.zeros(2),
            soc=np.zeros(2),
        )
        monkeypatch.setattr(kibam_mod, "validate_kibam_dispatch", lambda *a, **k: infeasible)

    def test_strict_true_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from samba._pipeline import _validate_kibam_if_needed
        from samba.compiler.constraints import ConstraintViolationError
        from samba.solver.runner import SolverConfig

        self._patch_infeasible(monkeypatch)
        with pytest.raises(ConstraintViolationError):
            _validate_kibam_if_needed(
                self._kibam_scenario(),
                self._dispatch_df(),
                SolverConfig(strict_kibam=True),
            )

    def test_strict_false_only_warns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from samba._pipeline import _validate_kibam_if_needed
        from samba.solver.runner import SolverConfig

        self._patch_infeasible(monkeypatch)
        # Must not raise — violations are logged as a warning only.
        _validate_kibam_if_needed(
            self._kibam_scenario(),
            self._dispatch_df(),
            SolverConfig(strict_kibam=False),
        )

    def test_validate_disabled_skips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from samba._pipeline import _validate_kibam_if_needed
        from samba.solver.runner import SolverConfig

        self._patch_infeasible(monkeypatch)
        # kibam_validate=False short-circuits before the check, so no raise.
        _validate_kibam_if_needed(
            self._kibam_scenario(),
            self._dispatch_df(),
            SolverConfig(strict_kibam=True, kibam_validate=False),
        )
