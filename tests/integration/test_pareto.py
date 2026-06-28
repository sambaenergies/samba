"""Integration tests for the Phase 12 Pareto sweep (cost vs emissions).

These tests invoke a real LP solver (HiGHS via ``highspy``).  They are
skipped automatically when HiGHS is not available.

Run:
    pytest tests/integration/test_pareto.py -v
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Module-level skip when HiGHS is unavailable
# ---------------------------------------------------------------------------

_highs_available = importlib.util.find_spec("highspy") is not None

pytestmark = [pytest.mark.integration, pytest.mark.slow]

skip_no_solver = pytest.mark.skipif(
    not _highs_available,
    reason="highspy not installed — run 'pip install highspy' or 'pip install -e .'",
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_N = 8760

# Flat 3 kW load
_LOAD_KW = np.full(_N, 3.0, dtype=np.float64)

# PV profile: 0.5 fraction for first 12 hours of each day, rest 0
_PV_PER_KWP = np.where(
    np.tile(np.concatenate([np.ones(12) * 0.5, np.zeros(12)]), 365),
    1.0,
    0.0,
).astype(np.float64)


def _make_scenario(**overrides: Any) -> Any:
    """Return a minimal but fully-valid Scenario for integration tests.

    Includes a flat-rate buy tariff so tariff resolution in samba.run()
    works without any CSV files.  Pass *overrides* as nested dicts to
    override any sub-section.
    """
    from samba.scenario.models import Scenario

    def _deep_update(base: dict, updates: dict) -> None:  # type: ignore[type-arg]
        for k, v in updates.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                _deep_update(base[k], v)
            else:
                base[k] = v

    base: dict[str, Any] = {
        "project": {
            "name": "pareto-integ-test",
            "discount_rate_nominal": 0.08,
            "lifetime_years": 20,
        },
        "location": {
            "latitude": 37.77,
            "longitude": -122.42,
            "timezone": "America/Los_Angeles",
        },
        "weather": {"source": "csv", "csv_path": "dummy.csv"},
        "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
        "components": {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 20.0},
            "pv": {"capex_per_kw": 1000.0, "capacity_kw": 10.0},
            "grid": {"capacity_kw": 50.0, "emission_factor_kg_per_kwh": 0.4},
        },
        "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.18}},
    }
    _deep_update(base, overrides)
    return Scenario.model_validate(base)


# ---------------------------------------------------------------------------
# 1. Single run: cost_and_emissions with alpha=0 behaves like cost-only
# ---------------------------------------------------------------------------


@skip_no_solver
class TestCostAndEmissionsAlphaZero:
    """Verified that alpha=0 produces identical NPC to cost-only objective."""

    def test_npc_same_as_cost_only(self, tmp_path: Path) -> None:
        import samba

        scene_cost = _make_scenario()
        scene_emi = _make_scenario(
            **{"objective": {"type": "cost_and_emissions", "emissions_weight": 0.0}}
        )

        result_cost = samba.run(scene_cost, load_kw=_LOAD_KW, pv_per_kwp=_PV_PER_KWP)
        result_emi = samba.run(scene_emi, load_kw=_LOAD_KW, pv_per_kwp=_PV_PER_KWP)

        assert result_cost.kpis["npc"] == pytest.approx(result_emi.kpis["npc"], rel=1e-4)

    def test_emissions_tracked_in_kpis(self) -> None:
        """total_emissions_kg should be present and non-negative in KPIs."""
        import samba

        scene = _make_scenario()
        result = samba.run(scene, load_kw=_LOAD_KW, pv_per_kwp=_PV_PER_KWP)

        assert "total_emissions_kg" in result.kpis
        assert result.kpis["total_emissions_kg"] >= 0.0


# ---------------------------------------------------------------------------
# 2. Pareto sweep: 3-point sweep on a PV+grid scenario
# ---------------------------------------------------------------------------


@skip_no_solver
class TestRunParetoSweep:
    """run_pareto_sweep returns plausible Pareto points."""

    def _run_sweep(self, tmp_path: Path, alphas: list[float]) -> list[Any]:
        from samba.pareto.sweep import run_pareto_sweep

        scene = _make_scenario()
        return run_pareto_sweep(
            scenario=scene,
            load_kw=_LOAD_KW,
            alphas=alphas,
            run_base_dir=tmp_path / "sweep",
            pv_per_kwp=_PV_PER_KWP,
        )

    def test_returns_correct_count(self, tmp_path: Path) -> None:
        pts = self._run_sweep(tmp_path, [0.0, 1.0, 10.0])
        # All 3 points should succeed (grid always feasible)
        assert len(pts) == 3

    def test_npc_nondecreasing(self, tmp_path: Path) -> None:
        """Higher alpha incurs higher NPC (or equal) — weighted cost increases."""
        pts = self._run_sweep(tmp_path, [0.0, 1.0, 10.0])
        npcs = [p.npc for p in pts]
        assert all(npcs[i] <= npcs[i + 1] + 1.0 for i in range(len(npcs) - 1)), (
            f"NPC should be non-decreasing but got {npcs}"
        )

    def test_first_point_is_alpha_zero(self, tmp_path: Path) -> None:
        pts = self._run_sweep(tmp_path, [0.0, 1.0, 10.0])
        assert pts[0].alpha == pytest.approx(0.0)

    def test_all_npc_positive(self, tmp_path: Path) -> None:
        pts = self._run_sweep(tmp_path, [0.0, 5.0])
        assert all(p.npc > 0.0 for p in pts)

    def test_all_lem_non_negative(self, tmp_path: Path) -> None:
        pts = self._run_sweep(tmp_path, [0.0, 5.0])
        assert all(p.lem >= 0.0 for p in pts)

    def test_dominated_flag_set(self, tmp_path: Path) -> None:
        """dominated field is a bool on every point."""
        pts = self._run_sweep(tmp_path, [0.0, 1.0, 10.0])
        assert all(isinstance(p.dominated, bool) for p in pts)

    def test_emissions_decline_with_alpha(self, tmp_path: Path) -> None:
        """Higher alpha should favour lower emissions solutions."""
        pts = self._run_sweep(tmp_path, [0.0, 50.0])
        if len(pts) == 2:
            # alpha=0 may have equal or higher emissions than alpha=50
            assert pts[1].total_emissions_kg <= pts[0].total_emissions_kg + 1.0


# ---------------------------------------------------------------------------
# 3. write_pareto_results produces correct output files
# ---------------------------------------------------------------------------


@skip_no_solver
class TestWriteParetoResults:
    """write_pareto_results creates expected CSV / JSON files."""

    def test_files_created(self, tmp_path: Path) -> None:
        from samba.pareto.sweep import ParetoPoint, write_pareto_results

        pts = [
            ParetoPoint(
                alpha=0.0,
                npc=150_000.0,
                lem=0.5,
                total_emissions_kg=1_200.0,
                sizing={"pv": 10.0, "battery": 20.0},
                run_dir=Path("."),
            ),
            ParetoPoint(
                alpha=1.0,
                npc=160_000.0,
                lem=0.4,
                total_emissions_kg=800.0,
                sizing={"pv": 15.0, "battery": 20.0},
                run_dir=Path("."),
            ),
        ]
        write_pareto_results(pts, tmp_path)

        assert (tmp_path / "pareto_front.csv").exists()
        assert (tmp_path / "pareto_front.json").exists()

    def test_csv_row_count(self, tmp_path: Path) -> None:
        """CSV has one header + one row per point."""
        import pandas as pd

        from samba.pareto.sweep import ParetoPoint, write_pareto_results

        pts = [
            ParetoPoint(alpha=0.0, npc=100_000.0, lem=0.6, total_emissions_kg=500.0),
            ParetoPoint(alpha=2.0, npc=105_000.0, lem=0.4, total_emissions_kg=300.0),
        ]
        write_pareto_results(pts, tmp_path)
        df = pd.read_csv(tmp_path / "pareto_front.csv")
        assert len(df) == 2

    def test_json_alpha_values(self, tmp_path: Path) -> None:
        """JSON contains correct alpha values."""
        import json

        from samba.pareto.sweep import ParetoPoint, write_pareto_results

        pts = [
            ParetoPoint(alpha=0.0, npc=100_000.0, lem=0.6, total_emissions_kg=500.0),
            ParetoPoint(alpha=5.0, npc=110_000.0, lem=0.3, total_emissions_kg=200.0),
        ]
        write_pareto_results(pts, tmp_path)
        data = json.loads((tmp_path / "pareto_front.json").read_text())
        alphas = [d["alpha"] for d in data]
        assert alphas == pytest.approx([0.0, 5.0])
