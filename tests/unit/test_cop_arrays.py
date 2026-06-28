# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for the physics-based (Carnot-fraction) COP model."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from samba.thermal.constants import COP_CEILING, COP_FLOOR
from samba.thermal.cop import (
    COPArrays,
    _indoor_wet_bulb,
    build_cop_arrays,
    compute_cooling_cop,
    compute_heating_cop,
)


class TestHeatingCOP:
    def test_cop_increases_with_temperature(self) -> None:
        """Heating COP rises as outdoor temp rises (smaller lift, easier heat)."""
        t = np.array([-10.0, 0.0, 10.0, 15.0])
        cop = compute_heating_cop(t)
        assert np.all(np.diff(cop) > 0), f"COP not monotonically increasing: {cop}"

    def test_cop_lower_bound_enforced(self) -> None:
        """COP must never fall below the floor (energy conservation)."""
        t = np.linspace(-30.0, 40.0, 100)
        cop = compute_heating_cop(t)
        assert float(np.min(cop)) >= COP_FLOOR

    def test_cop_upper_bound_enforced(self) -> None:
        """COP must not exceed the physical ceiling even at near-zero lift."""
        t = np.linspace(-30.0, 60.0, 100)
        cop = compute_heating_cop(t)
        assert float(np.max(cop)) <= COP_CEILING + 1e-6

    def test_cop_shape(self) -> None:
        """Output shape must match input shape."""
        t = np.zeros(8760)
        cop = compute_heating_cop(t)
        assert cop.shape == (8760,)

    def test_cop_all_finite(self) -> None:
        t = np.linspace(-30.0, 60.0, 8760)
        cop = compute_heating_cop(t)
        assert np.all(np.isfinite(cop))

    def test_typical_temperate_cop_above_three(self) -> None:
        """Mild-climate hours (5-15 deg C) should yield a heating COP above 3."""
        t = np.array([5.0, 10.0, 15.0])
        cop = compute_heating_cop(t)
        assert np.all(cop > 3.0)


class TestCoolingCOP:
    def test_cop_in_physical_range(self) -> None:
        t = np.array([25.0, 35.0, 40.0])
        cop = compute_cooling_cop(t)
        assert np.all(cop >= COP_FLOOR)
        assert np.all(cop <= COP_CEILING + 1e-6)

    def test_cop_decreases_with_temperature(self) -> None:
        """Cooling COP falls as outdoor temp rises (larger lift)."""
        t = np.array([25.0, 30.0, 35.0, 40.0])
        cop = compute_cooling_cop(t)
        assert np.all(np.diff(cop) < 0), f"COP not monotonically decreasing: {cop}"

    def test_cop_lower_bound_enforced(self) -> None:
        t = np.linspace(30.0, 55.0, 50)
        cop = compute_cooling_cop(t)
        assert float(np.min(cop)) >= COP_FLOOR

    def test_cop_shape_8760(self) -> None:
        t = np.linspace(10.0, 40.0, 8760)
        cop = compute_cooling_cop(t)
        assert cop.shape == (8760,)

    def test_cop_all_finite(self) -> None:
        t = np.linspace(-10.0, 50.0, 8760)
        cop = compute_cooling_cop(t)
        assert np.all(np.isfinite(cop))


class TestWetBulbTemperature:
    def test_t_iwb_reasonable_range(self) -> None:
        """Indoor wet-bulb at 22.22 deg C dry-bulb, RH~30% is ~10-14 deg C."""
        t_iwb = _indoor_wet_bulb(t_indoor=22.22, humidity_ratio=0.005, pressure_kpa=101.325)
        assert 8.0 <= t_iwb <= 16.0, f"T_iwb={t_iwb:.2f} deg C out of expected range [8, 16]"

    def test_t_iwb_less_than_dry_bulb(self) -> None:
        """Wet-bulb temperature must be <= dry-bulb temperature."""
        t_iwb = _indoor_wet_bulb(22.22, 0.005, 101.325)
        assert t_iwb < 22.22

    def test_t_iwb_increases_with_humidity(self) -> None:
        """More moisture in the indoor air raises the wet-bulb temperature."""
        dry = _indoor_wet_bulb(22.22, 0.004, 101.325)
        humid = _indoor_wet_bulb(22.22, 0.009, 101.325)
        assert humid > dry


class TestBuildCOPArrays:
    def _make_hp(self, **kwargs: Any) -> Any:
        from samba.scenario.models import HeatPump

        defaults: dict[str, Any] = {
            "enabled": True,
            "mode": "both",
            "sizing": "catalog_auto",
            "cop_source": "catalog",
        }
        defaults.update(kwargs)
        return HeatPump(**defaults)

    def test_both_mode_returns_two_arrays(self) -> None:
        hp = self._make_hp(mode="both")
        t = np.zeros(8760) + 5.0
        result = build_cop_arrays(hp, t)
        assert isinstance(result, COPArrays)
        assert result.heating is not None
        assert result.cooling is not None
        assert result.heating.shape == (8760,)
        assert result.cooling.shape == (8760,)

    def test_heating_only_mode_no_cooling_array(self) -> None:
        hp = self._make_hp(mode="heating_only")
        t = np.zeros(8760) + 5.0
        result = build_cop_arrays(hp, t)
        assert result.heating is not None
        assert result.cooling is None

    def test_cooling_only_mode_no_heating_array(self) -> None:
        hp = self._make_hp(mode="cooling_only")
        t = np.zeros(8760) + 30.0
        result = build_cop_arrays(hp, t)
        assert result.heating is None
        assert result.cooling is not None

    def test_fixed_cop_source_returns_constant(self) -> None:
        hp = self._make_hp(
            cop_source="fixed",
            fixed_cop_heating=3.5,
            fixed_cop_cooling=4.0,
        )
        t = np.linspace(-10.0, 40.0, 8760)
        result = build_cop_arrays(hp, t)
        assert result.heating is not None
        assert result.cooling is not None
        assert np.all(result.heating == pytest.approx(3.5))
        assert np.all(result.cooling == pytest.approx(4.0))

    def test_model_btu_and_name_set(self) -> None:
        hp = self._make_hp()
        t = np.zeros(8760)
        result = build_cop_arrays(hp, t, peak_heating_kw=5.0)
        assert result.model_btu in [18000, 24000, 30000, 36000, 42000, 48000, 60000]
        assert result.model_name != ""

    def test_capacities_match_catalog(self) -> None:
        from samba.thermal.hp_catalog import get_heating_capacity_kw

        hp = self._make_hp()
        t = np.zeros(8760)
        result = build_cop_arrays(hp, t, peak_heating_kw=5.0)
        expected_cap = get_heating_capacity_kw(result.model_btu)
        assert result.heating_capacity_kw == pytest.approx(expected_cap)
