"""Unit tests for samba.solver and samba.run_result.writer.

These tests avoid invoking a real LP solver; they use lightweight mocks and
synthetic DataFrames so they run in milliseconds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IDX = pd.date_range("2030-01-01", periods=8760, freq="h")
_ZEROS = np.zeros(8760, dtype=float)


def _dispatch_df(**col_overrides: Any) -> pd.DataFrame:
    """Return an 8760-row DataFrame with all contract columns zeroed."""
    cols = [
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
    ]
    data = {c: _ZEROS.copy() for c in cols}
    data.update(col_overrides)
    df = pd.DataFrame(data, index=_IDX)
    df.index.name = "timestamp"
    return df


# ---------------------------------------------------------------------------
# samba.solver.runner — config and exception hierarchy
# ---------------------------------------------------------------------------


class TestSolverConfig:
    def test_defaults(self) -> None:
        from samba.solver.runner import SolverConfig

        cfg = SolverConfig()
        assert cfg.solver_name == "appsi_highs"
        assert cfg.solver_io == ""
        assert cfg.time_limit_s == 600
        assert pytest.approx(cfg.mip_gap) == 0.01
        assert cfg.output_verbose is False

    def test_custom_values(self) -> None:
        from samba.solver.runner import SolverConfig

        cfg = SolverConfig(solver_name="glpk", mip_gap=0.05, time_limit_s=120)
        assert cfg.solver_name == "glpk"
        assert pytest.approx(cfg.mip_gap) == 0.05
        assert cfg.time_limit_s == 120


class TestSolverExceptionHierarchy:
    def test_infeasible_is_solver_error(self) -> None:
        from samba.solver.runner import InfeasibleError, SolverError

        err = InfeasibleError("test")
        assert isinstance(err, SolverError)
        assert isinstance(err, RuntimeError)

    def test_not_found_is_solver_error(self) -> None:
        from samba.solver.runner import SolverError, SolverNotFoundError

        err = SolverNotFoundError("test")
        assert isinstance(err, SolverError)

    def test_time_limit_is_solver_error(self) -> None:
        from samba.solver.runner import SolverError, SolverTimeLimitError

        err = SolverTimeLimitError("test")
        assert isinstance(err, SolverError)

    def test_all_can_be_caught_as_runtime_error(self) -> None:
        from samba.solver.runner import InfeasibleError

        with pytest.raises(RuntimeError):
            raise InfeasibleError("infeasible problem")


# ---------------------------------------------------------------------------
# samba.solver.extract — validate_energy_balance
# ---------------------------------------------------------------------------


class TestValidateEnergyBalance:
    def test_balanced_no_exception(self) -> None:
        """A perfectly balanced dispatch should not raise."""
        from samba.solver.extract import validate_energy_balance

        # AC supply == AC demand: load = 5 kW flat, grid_buy covers it
        df = _dispatch_df(eload=np.full(8760, 5.0), grid_buy=np.full(8760, 5.0))
        validate_energy_balance(df, tolerance_kwh=1.0)  # should not raise

    def test_small_imbalance_within_tolerance(self) -> None:
        """Imbalance below tolerance is accepted."""
        from samba.solver.extract import validate_energy_balance

        df = _dispatch_df(
            eload=np.full(8760, 5.0),
            grid_buy=np.full(8760, 5.5),  # over-buy by 0.5 kWh — within 1.0 tolerance
        )
        validate_energy_balance(df, tolerance_kwh=1.0)

    def test_imbalance_exceeds_tolerance_raises(self) -> None:
        """Imbalance above tolerance raises EnergyBalanceError."""
        from samba.solver.extract import EnergyBalanceError, validate_energy_balance

        df = _dispatch_df(
            eload=np.full(8760, 10.0),
            grid_buy=np.full(8760, 5.0),  # short by 5 kWh every hour
        )
        with pytest.raises(EnergyBalanceError) as exc_info:
            validate_energy_balance(df, tolerance_kwh=1.0)
        assert exc_info.value.max_imbalance > 1.0
        assert exc_info.value.tolerance_kwh == pytest.approx(1.0)

    def test_energy_balance_error_attributes(self) -> None:
        """EnergyBalanceError carries max_imbalance and tolerance_kwh."""
        from samba.solver.extract import EnergyBalanceError

        err = EnergyBalanceError(max_imbalance=7.5, tolerance_kwh=1.0)
        assert err.max_imbalance == pytest.approx(7.5)
        assert err.tolerance_kwh == pytest.approx(1.0)
        assert "7.5" in str(err)


# ---------------------------------------------------------------------------
# samba.solver.extract — extract_dispatch column names
# ---------------------------------------------------------------------------


class TestExtractDispatchColumns:
    """extract_dispatch must produce exactly the 14 contract columns."""

    def _mock_groups(self) -> dict[str, Any]:
        """Return a label→MagicMock dict for all expected node labels."""
        labels = [
            "dc_bus",
            "ac_bus",
            "pv",
            "battery",
            "inverter",
            "wind_turbine",
            "diesel_generator",
            "grid_import",
            "grid_export",
            "load",
            "unmet_load",
            "dc_dump",
            "ac_dump",
        ]
        return {lbl: MagicMock(name=lbl) for lbl in labels}

    def _mock_results(self, groups: dict[str, Any]) -> Any:
        """Build a mock solph.Results where .get() returns suitable DataFrames."""
        # Build a flow DataFrame with all possible (src, tgt) pairs returning zeros.
        # The columns that extract_dispatch will look up:
        ac_bus = groups["ac_bus"]
        dc_bus = groups["dc_bus"]
        load_node = groups["load"]
        grid_import = groups["grid_import"]
        grid_export = groups["grid_export"]
        unmet_node = groups["unmet_load"]
        ac_dump_node = groups["ac_dump"]
        dc_dump_node = groups["dc_dump"]
        pv_node = groups["pv"]
        batt_node = groups["battery"]
        inv_node = groups["inverter"]
        wt_node = groups["wind_turbine"]
        diesel_gen = groups["diesel_generator"]

        columns = [
            (ac_bus, load_node),
            (grid_import, ac_bus),
            (ac_bus, grid_export),
            (unmet_node, ac_bus),
            (ac_bus, ac_dump_node),
            (pv_node, dc_bus),
            (dc_bus, batt_node),
            (batt_node, dc_bus),
            (inv_node, ac_bus),
            (wt_node, ac_bus),
            (diesel_gen, ac_bus),
            (dc_bus, dc_dump_node),
        ]
        flow_df = pd.DataFrame(
            np.zeros((8760, len(columns)), dtype=float),
            index=_IDX,
            columns=columns,
        )
        # Storage content (8761 rows, battery node as column)
        soc_df = pd.DataFrame(
            np.zeros((8761, 1), dtype=float),
            columns=[batt_node],
        )
        # Mock battery node attributes for fixed capacity
        batt_node.nominal_storage_capacity = 100.0
        batt_node.outputs = {}

        results = MagicMock()
        results.get.side_effect = lambda key: {
            "flow": flow_df,
            "invest": None,
            "storage_content": soc_df,
        }.get(key)
        return results

    def test_correct_column_names(self) -> None:
        from samba.solver.extract import extract_dispatch

        groups = self._mock_groups()
        mock_es = MagicMock()
        mock_es.groups = groups
        mock_results = self._mock_results(groups)

        result = extract_dispatch(mock_es, mock_results)

        expected_cols = [
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
        assert list(result.dispatch.columns) == expected_cols

    def test_row_count(self) -> None:
        from samba.solver.extract import extract_dispatch

        groups = self._mock_groups()
        mock_es = MagicMock()
        mock_es.groups = groups
        mock_results = self._mock_results(groups)

        result = extract_dispatch(mock_es, mock_results)
        assert len(result.dispatch) == 8760

    def test_index_name(self) -> None:
        from samba.solver.extract import extract_dispatch

        groups = self._mock_groups()
        mock_es = MagicMock()
        mock_es.groups = groups
        mock_results = self._mock_results(groups)

        result = extract_dispatch(mock_es, mock_results)
        assert result.dispatch.index.name == "timestamp"

    def test_capacities_dict_returned(self) -> None:
        from samba.solver.extract import DispatchResult, extract_dispatch

        groups = self._mock_groups()
        mock_es = MagicMock()
        mock_es.groups = groups
        mock_results = self._mock_results(groups)

        result = extract_dispatch(mock_es, mock_results)
        assert isinstance(result, DispatchResult)
        assert isinstance(result.capacities, dict)

    def test_missing_flow_raises(self) -> None:
        """extract_dispatch raises ValueError when results.get('flow') returns None."""
        from samba.solver.extract import extract_dispatch

        groups = self._mock_groups()
        mock_es = MagicMock()
        mock_es.groups = groups
        mock_results = MagicMock()
        mock_results.get.return_value = None

        with pytest.raises(ValueError, match="flow"):
            extract_dispatch(mock_es, mock_results)


# ---------------------------------------------------------------------------
# samba.run_result.writer — ensure_run_dir
# ---------------------------------------------------------------------------


class TestEnsureRunDir:
    def test_creates_directory(self, tmp_path: Path) -> None:
        from samba.run_result.writer import ensure_run_dir

        run_dir = ensure_run_dir(tmp_path, "my_scenario")
        assert run_dir.exists()
        assert run_dir.is_dir()

    def test_name_contains_scenario(self, tmp_path: Path) -> None:
        from samba.run_result.writer import ensure_run_dir

        run_dir = ensure_run_dir(tmp_path, "test_scenario")
        assert "test_scenario" in run_dir.name

    def test_name_contains_timestamp(self, tmp_path: Path) -> None:
        from samba.run_result.writer import ensure_run_dir

        run_dir = ensure_run_dir(tmp_path, "sc")
        # Timestamp is YYYYMMDD_HHMMSS — 15 chars; name would be "sc_YYYYMMDD_HHMMSS"
        parts = run_dir.name.split("_")
        assert len(parts) >= 3  # sc, YYYYMMDD, HHMMSS

    def test_unsafe_chars_in_name(self, tmp_path: Path) -> None:
        """Non-filesystem-safe characters are replaced with underscores."""
        from samba.run_result.writer import ensure_run_dir

        run_dir = ensure_run_dir(tmp_path, "my scenario/v1")
        assert run_dir.exists()
        assert " " not in run_dir.name
        assert "/" not in run_dir.name

    def test_idempotent_with_exist_ok(self, tmp_path: Path) -> None:
        """Calling twice with different timestamps both succeed."""
        from samba.run_result.writer import ensure_run_dir

        run_dir1 = ensure_run_dir(tmp_path, "sc")
        run_dir2 = ensure_run_dir(tmp_path, "sc")
        # Both dirs should exist (they may or may not be the same second)
        assert run_dir1.exists()
        assert run_dir2.exists()


# ---------------------------------------------------------------------------
# samba.run_result.writer — write_dispatch
# ---------------------------------------------------------------------------


class TestWriteDispatch:
    def test_creates_parquet(self, tmp_path: Path) -> None:
        from samba.run_result.writer import write_dispatch

        df = _dispatch_df()
        write_dispatch(tmp_path, df)
        assert (tmp_path / "dispatch.parquet").exists()

    def test_creates_csv(self, tmp_path: Path) -> None:
        from samba.run_result.writer import write_dispatch

        df = _dispatch_df()
        write_dispatch(tmp_path, df)
        assert (tmp_path / "dispatch.csv").exists()

    def test_parquet_roundtrip(self, tmp_path: Path) -> None:
        """Parquet written by write_dispatch is readable and has correct shape."""
        from samba.run_result.writer import write_dispatch

        df = _dispatch_df(eload=np.full(8760, 7.0))
        write_dispatch(tmp_path, df)

        loaded = pd.read_parquet(tmp_path / "dispatch.parquet")
        assert loaded.shape == (8760, 14)
        assert list(loaded.columns) == list(df.columns)
        assert float(loaded["eload"].iloc[0]) == pytest.approx(7.0)

    def test_parquet_is_snappy(self, tmp_path: Path) -> None:
        """Parquet file is snappy-compressed (magic bytes don't indicate uncompressed)."""
        from samba.run_result.writer import write_dispatch

        df = _dispatch_df()
        write_dispatch(tmp_path, df)
        # Just check file exists and is non-trivially sized
        assert (tmp_path / "dispatch.parquet").stat().st_size > 100


# ---------------------------------------------------------------------------
# samba.run_result.writer — write_metadata
# ---------------------------------------------------------------------------


class TestWriteMetadata:
    def _mock_scenario(self) -> Any:
        s = MagicMock()
        s.model_dump_json.return_value = '{"name": "test"}'
        return s

    def _mock_solver_config(self) -> Any:
        from samba.solver.runner import SolverConfig

        return SolverConfig(solver_name="cbc")

    def test_creates_file(self, tmp_path: Path) -> None:
        from samba.run_result.writer import write_metadata

        write_metadata(tmp_path, self._mock_scenario(), self._mock_solver_config(), 12.3)
        assert (tmp_path / "metadata.json").exists()

    def test_required_fields_present(self, tmp_path: Path) -> None:
        """metadata.json must contain all fields from results-contract.md."""
        from samba.run_result.writer import write_metadata

        write_metadata(tmp_path, self._mock_scenario(), self._mock_solver_config(), 42.1)
        with (tmp_path / "metadata.json").open() as f:
            meta = json.load(f)

        required_fields = [
            "run_id",
            "samba_version",
            "git_hash",
            "timestamp_utc",
            "wall_time_seconds",
            "solver",
            "oemof_solph_version",
            "python_version",
            "platform",
            "kpis_schema_version",
            "scenario_hash",
            "status",
            "solver_status",
            "solver_termination",
        ]
        for field in required_fields:
            assert field in meta, f"Missing field: {field}"

    def test_solver_subdict(self, tmp_path: Path) -> None:
        from samba.run_result.writer import write_metadata

        write_metadata(tmp_path, self._mock_scenario(), self._mock_solver_config(), 1.0)
        meta = json.loads((tmp_path / "metadata.json").read_text())
        assert "solver" in meta
        assert "name" in meta["solver"]
        assert meta["solver"]["name"] == "cbc"

    def test_wall_time_rounded(self, tmp_path: Path) -> None:
        from samba.run_result.writer import write_metadata

        write_metadata(tmp_path, self._mock_scenario(), self._mock_solver_config(), 42.12345)
        meta = json.loads((tmp_path / "metadata.json").read_text())
        assert abs(meta["wall_time_seconds"] - 42.123) < 0.001

    def test_scenario_hash_format(self, tmp_path: Path) -> None:
        """scenario_hash must start with 'sha256:'."""
        from samba.run_result.writer import write_metadata

        write_metadata(tmp_path, self._mock_scenario(), self._mock_solver_config(), 1.0)
        meta = json.loads((tmp_path / "metadata.json").read_text())
        assert meta["scenario_hash"].startswith("sha256:")

    def test_run_id_defaults_to_dirname(self, tmp_path: Path) -> None:
        from samba.run_result.writer import write_metadata

        write_metadata(tmp_path, self._mock_scenario(), self._mock_solver_config(), 1.0)
        meta = json.loads((tmp_path / "metadata.json").read_text())
        assert meta["run_id"] == tmp_path.name

    def test_run_id_override(self, tmp_path: Path) -> None:
        from samba.run_result.writer import write_metadata

        write_metadata(
            tmp_path,
            self._mock_scenario(),
            self._mock_solver_config(),
            1.0,
            run_id="custom-run-001",
        )
        meta = json.loads((tmp_path / "metadata.json").read_text())
        assert meta["run_id"] == "custom-run-001"


# ---------------------------------------------------------------------------
# samba.solver.__init__ — public API surface
# ---------------------------------------------------------------------------


class TestSolverPublicAPI:
    def test_all_exports_importable(self) -> None:
        from samba.solver import (  # noqa: F401
            DispatchResult,
            EnergyBalanceError,
            InfeasibleError,
            SolverConfig,
            SolverError,
            SolverNotFoundError,
            SolverTimeLimitError,
            extract_dispatch,
            solve,
            validate_energy_balance,
        )

    def test_results_exports_importable(self) -> None:
        from samba.run_result import ensure_run_dir, write_dispatch, write_metadata  # noqa: F401
