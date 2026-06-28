# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for HP catalog model selection."""

from __future__ import annotations

import pytest

from samba.thermal.constants import BTU_PER_KWH, CATALOG_SIZES_BTU
from samba.thermal.hp_catalog import (
    get_cooling_capacity_kw,
    get_heating_capacity_kw,
    select_catalog_model,
)


class TestSelectCatalogModel:
    def test_small_demand_selects_smallest_model(self) -> None:
        """5 kW < 18000/3412 = 5.27 kW -- 18k model covers it."""
        assert select_catalog_model(5.0) == 18000

    def test_exact_boundary_selects_model_at_boundary(self) -> None:
        """Demand exactly equal to rated capacity → that model is selected."""
        rated_kw = 18000 / BTU_PER_KWH  # ~5.275 kW
        assert select_catalog_model(rated_kw) == 18000

    def test_10kw_selects_36k_model(self) -> None:
        """10 kW * 3412 = 34121 BTU/hr -- need 36000 (next above 30000 = 10.55 kW)."""
        # 30000 BTU/hr = 30000/3412 = 8.79 kW < 10 kW -> not enough
        # 36000 BTU/hr = 36000/3412 = 10.55 kW >= 10 kW -> selected
        assert select_catalog_model(10.0) == 36000

    def test_demand_above_catalog_max_raises(self) -> None:
        """Demand > 60000 BTU/hr (17.58 kW) raises ValueError."""
        with pytest.raises(ValueError, match="exceeds the largest catalog model"):
            select_catalog_model(20.0)

    def test_17kw_selects_60k_model(self) -> None:
        """17 kW * 3412 = 58006 BTU/hr -- 60000 BTU/hr model covers it."""
        assert select_catalog_model(17.0) == 60000

    def test_zero_demand_selects_smallest_model(self) -> None:
        """Zero demand (no thermal load configured yet) → smallest model."""
        assert select_catalog_model(0.0) == CATALOG_SIZES_BTU[0]

    def test_negative_demand_treated_as_zero(self) -> None:
        """Negative demand (shouldn't occur) is handled like zero."""
        # negative <= 0.0 branch → smallest model
        assert select_catalog_model(-1.0) == CATALOG_SIZES_BTU[0]

    def test_all_catalog_sizes_selectable(self) -> None:
        """Each catalog size can be selected by setting demand slightly below its rated kW."""
        for size_btu in CATALOG_SIZES_BTU:
            # Demand just under rated capacity -> this model is the first that covers it
            demand_kw = (size_btu - 1) / BTU_PER_KWH
            result = select_catalog_model(demand_kw)
            assert result == size_btu, (
                f"Expected {size_btu} BTU/hr for {demand_kw:.3f} kW demand, got {result}"
            )


class TestCapacityHelpers:
    def test_heating_capacity_18k(self) -> None:
        assert get_heating_capacity_kw(18000) == pytest.approx(18000 / 3412.142)

    def test_cooling_capacity_equals_heating_capacity(self) -> None:
        """Catalog uses the same rated BTU/hr for both modes."""
        for size in CATALOG_SIZES_BTU:
            assert get_heating_capacity_kw(size) == pytest.approx(get_cooling_capacity_kw(size))
