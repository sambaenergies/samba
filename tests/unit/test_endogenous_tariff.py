# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for endogenous tiered tariff schema and cost arithmetic.

Covers:
- BuyRate.endogenous_tiering schema validation
- Manual tier cost arithmetic (expected cost for given consumption values)
- monthly_grid_kwh / monthly_grid_cost KPI fields
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from samba.scenario.models import BuyRate, TierLevel

# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestEndogenousTieringSchema:
    def test_endogenous_defaults_false(self) -> None:
        buy = BuyRate(
            type="tiered",
            tiers=[TierLevel(limit_kwh=500, rate_per_kwh=0.10), TierLevel(rate_per_kwh=0.20)],
        )
        assert buy.endogenous_tiering is False

    def test_endogenous_true_allowed_for_tiered(self) -> None:
        buy = BuyRate(
            type="tiered",
            tiers=[TierLevel(limit_kwh=500, rate_per_kwh=0.10), TierLevel(rate_per_kwh=0.20)],
            endogenous_tiering=True,
        )
        assert buy.endogenous_tiering is True

    def test_endogenous_true_allowed_for_seasonal_tiered(self) -> None:
        from samba.scenario.models import SeasonalTiers

        buy = BuyRate(
            type="seasonal_tiered",
            seasonal_tiers=[
                SeasonalTiers(
                    name="all_year",
                    months=list(range(1, 13)),
                    tiers=[
                        TierLevel(limit_kwh=500, rate_per_kwh=0.10),
                        TierLevel(rate_per_kwh=0.20),
                    ],
                )
            ],
            endogenous_tiering=True,
        )
        assert buy.endogenous_tiering is True

    def test_endogenous_true_allowed_for_monthly_tiered(self) -> None:
        tiers_row = [TierLevel(limit_kwh=500, rate_per_kwh=0.10), TierLevel(rate_per_kwh=0.20)]
        buy = BuyRate(
            type="monthly_tiered",
            monthly_tiers=[tiers_row] * 12,
            endogenous_tiering=True,
        )
        assert buy.endogenous_tiering is True

    def test_endogenous_true_rejected_for_flat(self) -> None:
        with pytest.raises(ValueError, match="endogenous_tiering only applicable"):
            BuyRate(type="flat", rate_per_kwh=0.15, endogenous_tiering=True)

    def test_endogenous_true_rejected_for_tou(self) -> None:
        from samba.scenario.models import TouPeriod

        with pytest.raises(ValueError, match="endogenous_tiering only applicable"):
            BuyRate(
                type="tou",
                tou_schedule=[TouPeriod(name="peak", hours=list(range(8, 21)), rate_per_kwh=0.25)],
                endogenous_tiering=True,
            )

    def test_endogenous_true_rejected_for_seasonal(self) -> None:
        from samba.scenario.models import SeasonalRate

        with pytest.raises(ValueError, match="endogenous_tiering only applicable"):
            BuyRate(
                type="seasonal",
                seasonal_schedule=[
                    SeasonalRate(name="all", months=list(range(1, 13)), rate_per_kwh=0.15)
                ],
                endogenous_tiering=True,
            )


# ---------------------------------------------------------------------------
# Tier cost arithmetic
# ---------------------------------------------------------------------------
#
# Tier structure: 0-500 kWh @ $0.10, 500-1000 kWh @ $0.15, >1000 kWh @ $0.20
#
# Correct tier costs:
#   450 kWh → all in tier 0: 450 × 0.10 = $45.00
#   600 kWh → 500 in tier 0 + 100 in tier 1: 500×0.10 + 100×0.15 = $50 + $15 = $65.00
#   1200 kWh → 500 in tier 0 + 500 in tier 1 + 200 in tier 2:
#              500×0.10 + 500×0.15 + 200×0.20 = $50 + $75 + $40 = $165.00


def _tier_cost(kwh: float) -> float:
    """Manual reference implementation of 3-tier cost calculation."""
    if kwh <= 500:
        return kwh * 0.10
    elif kwh <= 1000:
        return 500 * 0.10 + (kwh - 500) * 0.15
    else:
        return 500 * 0.10 + 500 * 0.15 + (kwh - 1000) * 0.20


class TestTierCostArithmetic:
    def test_450_kwh_all_in_tier_0(self) -> None:
        assert _tier_cost(450) == pytest.approx(45.00)

    def test_600_kwh_spans_tiers_0_and_1(self) -> None:
        assert _tier_cost(600) == pytest.approx(65.00)

    def test_1200_kwh_spans_all_three_tiers(self) -> None:
        assert _tier_cost(1200) == pytest.approx(165.00)

    def test_zero_kwh_costs_zero(self) -> None:
        assert _tier_cost(0) == pytest.approx(0.0)

    def test_exactly_at_first_boundary(self) -> None:
        # 500 kWh = exactly the first tier limit
        assert _tier_cost(500) == pytest.approx(50.00)

    def test_exactly_at_second_boundary(self) -> None:
        # 1000 kWh fills both lower tiers exactly
        assert _tier_cost(1000) == pytest.approx(50.00 + 75.00)


# ---------------------------------------------------------------------------
# Monthly KPI list shape and type
# ---------------------------------------------------------------------------


class TestMonthlyKpiFields:
    def _run_compute_kpis(
        self, grid_buy_kw: float = 2.0, cbuy: float = 0.2
    ) -> tuple[list[Any], list[Any]]:
        """Run compute_kpis with a simple synthetic scenario and return monthly lists."""

        from samba.run_result.kpis import compute_kpis
        from samba.scenario.models import (
            PV,
            Battery,
            Components,
            Grid,
            Inverter,
            Load,
            Location,
            Project,
            Scenario,
        )
        from samba.tariff.resolver import TariffArrays

        # Minimal scenario (same helpers as test_economics.py)
        project = Project(
            name="test",
            discount_rate_nominal=0.08,
            lifetime_years=25,
        )
        location = Location(latitude=0.0, longitude=0.0, timezone="UTC")
        load = Load(source="hourly_csv", csv_path="dummy.csv")
        pv = PV(capacity_kw=10.0, capex_per_kw=1000.0)
        battery = Battery(capacity_kwh=20.0, capex_per_kwh=300.0)
        inverter = Inverter(capacity_kw=10.0, capex_per_kw=200.0)
        grid = Grid(capacity_kw=20.0)
        components = Components(pv=pv, battery=battery, inverter=inverter, grid=grid)
        from samba.scenario.models import BuyRate
        from samba.scenario.models import Tariff as TariffModel

        tariff = TariffModel(buy=BuyRate(type="flat", rate_per_kwh=cbuy))
        from samba.scenario.models import Weather

        weather = Weather(source="csv", csv_path="dummy.csv")
        scenario = Scenario(
            project=project,
            location=location,
            weather=weather,
            load=load,
            components=components,
            tariff=tariff,
        )

        # Build a DispatchResult-like structure
        import pandas as pd

        from samba.solver.extract import DispatchResult

        N = 8760
        dispatch = pd.DataFrame(
            {
                "eload": np.full(N, grid_buy_kw),
                "unmet_load": np.zeros(N),
                "pv_gen": np.zeros(N),
                "wt_gen": np.zeros(N),
                "dg_gen": np.zeros(N),
                "grid_buy": np.full(N, grid_buy_kw),
                "grid_sell": np.zeros(N),
                "energy_dump": np.zeros(N),
                "batt_charge": np.zeros(N),
                "batt_discharge": np.zeros(N),
                "battery_soc_kwh": np.zeros(N),
            }
        )
        caps = {"pv_kw": 10.0, "battery_kwh": 20.0, "inverter_kw": 10.0}
        dr = DispatchResult(dispatch=dispatch, capacities=caps)

        cbuy_arr = np.full(N, cbuy)
        tariff_arrays = TariffArrays(cbuy=cbuy_arr, csell=np.zeros(N), service_charge=np.zeros(12))
        kpis, _, _ = compute_kpis(scenario, dr, tariff_arrays)
        return kpis["monthly_grid_kwh"], kpis["monthly_grid_cost"]

    def test_monthly_grid_kwh_is_list_of_12(self) -> None:
        kwh_list, _ = self._run_compute_kpis()
        assert len(kwh_list) == 12

    def test_monthly_grid_cost_is_list_of_12(self) -> None:
        _, cost_list = self._run_compute_kpis()
        assert len(cost_list) == 12

    def test_monthly_grid_kwh_sums_to_annual_total(self) -> None:
        kwh_list, _ = self._run_compute_kpis(grid_buy_kw=1.0)
        # 1.0 kW × 8760 h = 8760 kWh
        assert sum(kwh_list) == pytest.approx(8760.0, rel=1e-4)

    def test_monthly_grid_cost_proportional_to_rate(self) -> None:
        _, cost_low = self._run_compute_kpis(grid_buy_kw=1.0, cbuy=0.10)
        _, cost_high = self._run_compute_kpis(grid_buy_kw=1.0, cbuy=0.20)
        # Higher rate → double the cost
        assert sum(cost_high) == pytest.approx(2 * sum(cost_low), rel=1e-4)

    def test_january_matches_expected_hours(self) -> None:
        kwh_list, _ = self._run_compute_kpis(grid_buy_kw=1.0)
        # January = 31 days × 24 h × 1 kW = 744 kWh
        assert kwh_list[0] == pytest.approx(744.0, rel=1e-4)

    def test_february_matches_expected_hours(self) -> None:
        kwh_list, _ = self._run_compute_kpis(grid_buy_kw=1.0)
        # February = 28 days × 24 h × 1 kW = 672 kWh
        assert kwh_list[1] == pytest.approx(672.0, rel=1e-4)
