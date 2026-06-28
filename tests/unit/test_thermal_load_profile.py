# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for Phase 22 thermal load profiles.

Tests cover:
  - ``ThermalLoads`` dataclass properties.
  - ``_load_csv`` helper (via ``load_thermal_loads`` with source='csv').
  - ``_degree_day_loads`` helper (via ``load_thermal_loads`` with source='degree_day').
  - ``load_thermal_loads`` dispatcher including error cases.
  - ``ThermalLoad`` Pydantic schema validation (full Phase 22 schema).
"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

_HOURS = 8760


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, values: np.ndarray) -> None:
    """Write a single-column CSV to *path*."""
    pd.DataFrame({"kw_th": values}).to_csv(path, index=False)


def _sine_heat(amplitude: float = 5.0, offset: float = 5.0) -> np.ndarray:
    """Produce a synthetic 8760-element heating profile (non-negative)."""
    t = np.linspace(0, 2 * np.pi, _HOURS)
    return np.maximum(offset + amplitude * np.sin(t + np.pi), 0.0)


def _const(value: float, n: int = _HOURS) -> np.ndarray:
    return np.full(n, value, dtype=float)


# ---------------------------------------------------------------------------
# ThermalLoads dataclass
# ---------------------------------------------------------------------------


class TestThermalLoads:
    """Tests for the ThermalLoads container."""

    def test_properties_nonzero(self) -> None:
        from samba.load_profiles.thermal import ThermalLoads

        h = _const(3.0)
        c = _const(2.0)
        tl = ThermalLoads(heating=h, cooling=c)
        assert tl.peak_heating_kw == pytest.approx(3.0)
        assert tl.peak_cooling_kw == pytest.approx(2.0)
        assert tl.annual_heating_kwh_th == pytest.approx(3.0 * _HOURS)
        assert tl.annual_cooling_kwh_th == pytest.approx(2.0 * _HOURS)

    def test_properties_zeros(self) -> None:
        from samba.load_profiles.thermal import ThermalLoads

        tl = ThermalLoads(heating=np.zeros(_HOURS), cooling=np.zeros(_HOURS))
        assert tl.peak_heating_kw == pytest.approx(0.0)
        assert tl.peak_cooling_kw == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------


class TestLoadCsv:
    """Tests for the CSV loading path."""

    def test_heating_only(self) -> None:
        from samba.load_profiles.thermal import load_thermal_loads
        from samba.scenario.models import ThermalLoad

        with tempfile.TemporaryDirectory() as tmp:
            h_path = Path(tmp) / "heating.csv"
            arr = _sine_heat()
            _write_csv(h_path, arr)
            cfg = ThermalLoad(source="csv", heating_csv_path=str(h_path))
            tl = load_thermal_loads(cfg)
        np.testing.assert_allclose(tl.heating, arr)
        np.testing.assert_allclose(tl.cooling, np.zeros(_HOURS))

    def test_cooling_only(self) -> None:
        from samba.load_profiles.thermal import load_thermal_loads
        from samba.scenario.models import ThermalLoad

        with tempfile.TemporaryDirectory() as tmp:
            c_path = Path(tmp) / "cooling.csv"
            arr = _const(4.0)
            _write_csv(c_path, arr)
            cfg = ThermalLoad(source="csv", cooling_csv_path=str(c_path))
            tl = load_thermal_loads(cfg)
        np.testing.assert_allclose(tl.cooling, arr)
        np.testing.assert_allclose(tl.heating, np.zeros(_HOURS))

    def test_both_paths(self) -> None:
        from samba.load_profiles.thermal import load_thermal_loads
        from samba.scenario.models import ThermalLoad

        h_arr = _sine_heat()
        c_arr = _const(1.5)
        with tempfile.TemporaryDirectory() as tmp:
            h_path = Path(tmp) / "h.csv"
            c_path = Path(tmp) / "c.csv"
            _write_csv(h_path, h_arr)
            _write_csv(c_path, c_arr)
            cfg = ThermalLoad(
                source="csv",
                heating_csv_path=str(h_path),
                cooling_csv_path=str(c_path),
            )
            tl = load_thermal_loads(cfg)
        np.testing.assert_allclose(tl.heating, h_arr)
        np.testing.assert_allclose(tl.cooling, c_arr)

    def test_wrong_length_raises(self) -> None:
        from samba.load_profiles.thermal import load_thermal_loads
        from samba.scenario.models import ThermalLoad

        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "bad.csv"
            _write_csv(bad_path, np.ones(100))
            cfg = ThermalLoad(source="csv", heating_csv_path=str(bad_path))
            with pytest.raises(ValueError, match="8760"):
                load_thermal_loads(cfg)

    def test_negative_values_raises(self) -> None:
        from samba.load_profiles.thermal import load_thermal_loads
        from samba.scenario.models import ThermalLoad

        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "neg.csv"
            arr = np.full(_HOURS, -1.0)
            _write_csv(bad_path, arr)
            cfg = ThermalLoad(source="csv", heating_csv_path=str(bad_path))
            with pytest.raises(ValueError, match="negative"):
                load_thermal_loads(cfg)


# ---------------------------------------------------------------------------
# Degree-day loading
# ---------------------------------------------------------------------------


class TestDegreeDayLoads:
    """Tests for the degree-day loading path."""

    def _cold_climate(self) -> np.ndarray:
        """8760-element outdoor temperature: cold winter scenario."""
        t = np.linspace(0, 2 * np.pi, _HOURS)
        # Ranges from ~-10°C (winter) to ~20°C (summer)
        return 5.0 + 15.0 * np.sin(t - np.pi / 2)

    def test_heating_demand_positive(self) -> None:
        from samba.load_profiles.thermal import load_thermal_loads
        from samba.scenario.models import ThermalLoad

        cfg = ThermalLoad(
            source="degree_day",
            building_ua_kw_per_k=0.5,
            heating_setpoint_c=20.0,
            cooling_setpoint_c=24.0,
            distribution_efficiency=1.0,
        )
        t_out = self._cold_climate()
        tl = load_thermal_loads(cfg, t_outdoor=t_out)
        # There must be some heating demand in this cold climate
        assert tl.annual_heating_kwh_th > 0.0

    def test_zero_cooling_in_cold_climate(self) -> None:
        from samba.load_profiles.thermal import load_thermal_loads
        from samba.scenario.models import ThermalLoad

        cfg = ThermalLoad(
            source="degree_day",
            building_ua_kw_per_k=0.5,
            heating_setpoint_c=20.0,
            cooling_setpoint_c=24.0,
            distribution_efficiency=1.0,
        )
        t_out = np.full(_HOURS, -5.0)  # always freezing: no cooling
        tl = load_thermal_loads(cfg, t_outdoor=t_out)
        assert tl.annual_cooling_kwh_th == pytest.approx(0.0)

    def test_distribution_efficiency_scales_demand(self) -> None:
        from samba.load_profiles.thermal import load_thermal_loads
        from samba.scenario.models import ThermalLoad

        t_out = np.full(_HOURS, 0.0)  # 0°C -> 20K below setpoint
        cfg_full = ThermalLoad(
            source="degree_day",
            building_ua_kw_per_k=1.0,
            heating_setpoint_c=20.0,
            cooling_setpoint_c=24.0,
            distribution_efficiency=1.0,
        )
        cfg_partial = ThermalLoad(
            source="degree_day",
            building_ua_kw_per_k=1.0,
            heating_setpoint_c=20.0,
            cooling_setpoint_c=24.0,
            distribution_efficiency=0.8,
        )
        tl_full = load_thermal_loads(cfg_full, t_outdoor=t_out)
        tl_partial = load_thermal_loads(cfg_partial, t_outdoor=t_out)
        # Lower efficiency -> higher supply-side demand
        assert tl_partial.annual_heating_kwh_th == pytest.approx(
            tl_full.annual_heating_kwh_th / 0.8, rel=1e-6
        )

    def test_separate_ua_cool(self) -> None:
        from samba.load_profiles.thermal import load_thermal_loads
        from samba.scenario.models import ThermalLoad

        t_out = np.full(_HOURS, 30.0)  # 30°C -> 6K above cooling setpoint
        cfg = ThermalLoad(
            source="degree_day",
            building_ua_kw_per_k=1.0,
            building_ua_cool_kw_per_k=2.0,
            heating_setpoint_c=20.0,
            cooling_setpoint_c=24.0,
            distribution_efficiency=1.0,
        )
        tl = load_thermal_loads(cfg, t_outdoor=t_out)
        # With T=30°C, UA_cool=2: q_cool = 2*(30-24) = 12 kW per hour
        assert tl.peak_cooling_kw == pytest.approx(12.0, rel=1e-6)

    def test_missing_t_outdoor_raises(self) -> None:
        from samba.load_profiles.thermal import load_thermal_loads
        from samba.scenario.models import ThermalLoad

        cfg = ThermalLoad(
            source="degree_day",
            building_ua_kw_per_k=0.5,
        )
        with pytest.raises(ValueError, match="t_outdoor"):
            load_thermal_loads(cfg, t_outdoor=None)

    def test_wrong_t_outdoor_length_raises(self) -> None:
        from samba.load_profiles.thermal import load_thermal_loads
        from samba.scenario.models import ThermalLoad

        cfg = ThermalLoad(
            source="degree_day",
            building_ua_kw_per_k=0.5,
        )
        with pytest.raises(ValueError, match="8760"):
            load_thermal_loads(cfg, t_outdoor=np.zeros(100))


# ---------------------------------------------------------------------------
# ThermalLoad schema validation
# ---------------------------------------------------------------------------


_BASE_SCENARIO: dict[str, Any] = {
    "project": {"name": "test", "discount_rate_nominal": 0.08},
    "location": {"latitude": 51.5, "longitude": -0.12, "timezone": "Europe/London"},
    "weather": {"source": "csv", "csv_path": "dummy.csv"},
    "load": {"source": "hourly_csv", "csv_path": "dummy.csv"},
    "components": {
        "inverter": {"capex_per_kw": 200.0, "capacity_kw": 50.0},
        "grid": {"capacity_kw": 100.0},
    },
    "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.12}},
}


def _scenario_with_thermal(thermal_dict: dict[str, Any]) -> Any:
    from samba.scenario.models import Scenario

    data = copy.deepcopy(_BASE_SCENARIO)
    data["load"]["thermal"] = thermal_dict
    return Scenario.model_validate(data)


class TestThermalLoadSchema:
    """Tests for ThermalLoad Pydantic model validation."""

    def test_csv_valid_heating_only(self) -> None:
        s = _scenario_with_thermal({"source": "csv", "heating_csv_path": "h.csv"})
        assert s.load.thermal.heating_csv_path == "h.csv"

    def test_csv_valid_both_paths(self) -> None:
        s = _scenario_with_thermal(
            {"source": "csv", "heating_csv_path": "h.csv", "cooling_csv_path": "c.csv"}
        )
        assert s.load.thermal.cooling_csv_path == "c.csv"

    def test_csv_missing_both_paths_raises(self) -> None:
        with pytest.raises(ValidationError, match="at least one"):
            _scenario_with_thermal({"source": "csv"})

    def test_degree_day_valid(self) -> None:
        s = _scenario_with_thermal({"source": "degree_day", "building_ua_kw_per_k": 0.5})
        assert s.load.thermal.building_ua_kw_per_k == pytest.approx(0.5)

    def test_degree_day_missing_ua_raises(self) -> None:
        with pytest.raises(ValidationError, match="building_ua_kw_per_k"):
            _scenario_with_thermal({"source": "degree_day"})

    def test_inverted_setpoints_raises(self) -> None:
        with pytest.raises(ValidationError, match="heating_setpoint_c must be less"):
            _scenario_with_thermal(
                {
                    "source": "csv",
                    "heating_csv_path": "h.csv",
                    "heating_setpoint_c": 25.0,
                    "cooling_setpoint_c": 20.0,
                }
            )

    def test_equal_setpoints_raises(self) -> None:
        with pytest.raises(ValidationError, match="heating_setpoint_c must be less"):
            _scenario_with_thermal(
                {
                    "source": "csv",
                    "heating_csv_path": "h.csv",
                    "heating_setpoint_c": 20.0,
                    "cooling_setpoint_c": 20.0,
                }
            )

    def test_invalid_efficiency_raises(self) -> None:
        with pytest.raises(ValidationError, match="distribution_efficiency"):
            _scenario_with_thermal(
                {
                    "source": "csv",
                    "heating_csv_path": "h.csv",
                    "distribution_efficiency": 0.0,
                }
            )

    def test_efficiency_above_one_raises(self) -> None:
        with pytest.raises(ValidationError, match="distribution_efficiency"):
            _scenario_with_thermal(
                {
                    "source": "csv",
                    "heating_csv_path": "h.csv",
                    "distribution_efficiency": 1.1,
                }
            )

    def test_extra_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            _scenario_with_thermal(
                {"source": "csv", "heating_csv_path": "h.csv", "nonexistent_field": 1}
            )


class TestConstraintsThermalLpspMax:
    """Tests for the Constraints.thermal_lpsp_max field."""

    def _make_scenario(self, thermal_lpsp_max: float) -> Any:
        from samba.scenario.models import Scenario

        data = copy.deepcopy(_BASE_SCENARIO)
        data["constraints"] = {"thermal_lpsp_max": thermal_lpsp_max}
        return Scenario.model_validate(data)

    def test_default_is_zero(self) -> None:
        from samba.scenario.models import Scenario

        s = Scenario.model_validate(_BASE_SCENARIO)
        assert s.constraints.thermal_lpsp_max == pytest.approx(0.0)

    def test_valid_value(self) -> None:
        s = self._make_scenario(0.05)
        assert s.constraints.thermal_lpsp_max == pytest.approx(0.05)

    def test_boundary_zero(self) -> None:
        s = self._make_scenario(0.0)
        assert s.constraints.thermal_lpsp_max == pytest.approx(0.0)

    def test_boundary_one(self) -> None:
        s = self._make_scenario(1.0)
        assert s.constraints.thermal_lpsp_max == pytest.approx(1.0)

    def test_above_one_raises(self) -> None:
        with pytest.raises(ValidationError, match="thermal_lpsp_max"):
            self._make_scenario(1.1)

    def test_negative_raises(self) -> None:
        with pytest.raises(ValidationError, match="thermal_lpsp_max"):
            self._make_scenario(-0.01)
