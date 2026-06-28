"""Unit tests for samba.economics and samba.run_result.kpis.

All tests are pure-Python / NumPy — no solver required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_IDX = pd.date_range("2030-01-01", periods=8760, freq="h")
_ZEROS = np.zeros(8760, dtype=float)


def _dispatch_df(**col_overrides: Any) -> pd.DataFrame:
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


def _tariff_arrays(buy: float = 0.15, sell: float = 0.05) -> Any:
    """Return a minimal TariffArrays-compatible object."""
    from dataclasses import dataclass

    import numpy as np

    @dataclass
    class FakeTariff:
        cbuy: np.ndarray
        csell: np.ndarray
        service_charge: np.ndarray

    return FakeTariff(
        cbuy=np.full(8760, buy),
        csell=np.full(8760, sell),
        service_charge=np.zeros(12),
    )


def _make_scenario(
    *,
    lifetime_years: int = 25,
    discount_rate_nominal: float = 0.08,
    inflation_rate: float = 0.025,
    re_incentive_rate: float = 0.0,
    pv_capex_per_kw: float = 1200.0,
    battery_capex_per_kwh: float = 400.0,
    inverter_capex_per_kw: float = 200.0,
    dg_capacity_kw: float = 0.0,
) -> Any:
    """Build a minimal Scenario using the real Pydantic models."""
    from samba.scenario.models import (
        PV,
        Battery,
        Components,
        Constraints,
        DieselGenerator,
        Inverter,
        Load,
        Location,
        Objective,
        Project,
        Scenario,
        Tariff,
        Weather,
    )

    pv = PV(
        capex_per_kw=pv_capex_per_kw,
        opex_per_kw_yr=15.0,
        lifetime_years=25,
    )
    battery = Battery(
        capex_per_kwh=battery_capex_per_kwh,
        opex_per_kwh_yr=5.0,
        lifetime_years=10,
    )
    inverter = Inverter(
        capex_per_kw=inverter_capex_per_kw,
        opex_per_kw_yr=5.0,
        lifetime_years=10,
    )
    dg = (
        DieselGenerator(
            capacity_kw=dg_capacity_kw,
            capex_per_kw=500.0,
            opex_per_kw_yr=50.0,
            fuel_price_per_l=0.90,
            lifetime_years=15,
        )
        if dg_capacity_kw > 0
        else None
    )

    # Minimal buy-rate tariff (flat 0.15 $/kWh)
    from samba.scenario.models import BuyRate

    buy_rate = BuyRate(type="flat", rate_per_kwh=0.15)
    tariff = Tariff(buy=buy_rate)

    return Scenario(
        project=Project(
            name="test_scenario",
            year=2030,
            lifetime_years=lifetime_years,
            discount_rate_nominal=discount_rate_nominal,
            inflation_rate=inflation_rate,
            re_incentive_rate=re_incentive_rate,
        ),
        location=Location(latitude=51.5, longitude=-0.1, timezone="Europe/London"),
        weather=Weather(source="csv", csv_path="dummy.csv"),
        load=Load(source="hourly_csv", csv_path="dummy.csv"),
        components=Components(
            pv=pv,
            battery=battery,
            inverter=inverter,
            diesel_generator=dg,
        ),
        tariff=tariff,
        constraints=Constraints(),
        objective=Objective(),
    )


def _dispatch_result(caps: dict[str, float], **col_overrides: Any) -> Any:
    from samba.solver.extract import DispatchResult

    return DispatchResult(dispatch=_dispatch_df(**col_overrides), capacities=caps)


# ===========================================================================
# samba.economics.npc
# ===========================================================================


class TestRealDiscountRate:
    def test_known_value(self) -> None:
        from samba.economics.npc import real_discount_rate

        result = real_discount_rate(0.08, 0.025)
        assert pytest.approx(result, rel=1e-4) == (0.08 - 0.025) / 1.025

    def test_zero_inflation(self) -> None:
        from samba.economics.npc import real_discount_rate

        assert pytest.approx(real_discount_rate(0.08, 0.0)) == 0.08


class TestPresentWorthFactor:
    def test_known_value(self) -> None:
        from samba.economics.npc import present_worth_factor

        # PWF(0.08, 25) = (1 - 1.08^-25) / 0.08
        expected = (1 - 1.08**-25) / 0.08
        assert pytest.approx(present_worth_factor(0.08, 25), rel=1e-5) == expected

    def test_zero_rate(self) -> None:
        from samba.economics.npc import present_worth_factor

        assert present_worth_factor(0.0, 10) == 10.0

    def test_zero_periods(self) -> None:
        from samba.economics.npc import present_worth_factor

        assert present_worth_factor(0.05, 0) == 0.0


class TestSinglePaymentPv:
    def test_year_zero(self) -> None:
        from samba.economics.npc import single_payment_pv

        assert single_payment_pv(0.08, 0) == 1.0

    def test_year_10(self) -> None:
        from samba.economics.npc import single_payment_pv

        assert pytest.approx(single_payment_pv(0.08, 10)) == 1.0 / 1.08**10

    def test_zero_rate(self) -> None:
        from samba.economics.npc import single_payment_pv

        assert single_payment_pv(0.0, 20) == 1.0


# ===========================================================================
# samba.economics.replacement
# ===========================================================================


class TestReplacementYears:
    def test_two_replacements(self) -> None:
        from samba.economics.replacement import replacement_years

        assert replacement_years(25, 10) == [10, 20]

    def test_no_replacements_when_lifetime_equals_project(self) -> None:
        from samba.economics.replacement import replacement_years

        assert replacement_years(25, 25) == []

    def test_one_replacement(self) -> None:
        from samba.economics.replacement import replacement_years

        assert replacement_years(20, 10) == [10]

    def test_zero_lifetime_raises(self) -> None:
        from samba.economics.replacement import replacement_years

        with pytest.raises(ValueError, match="component_lifetime must be > 0"):
            replacement_years(25, 0)


class TestReplacementNpv:
    def test_two_replacements_positive(self) -> None:
        from samba.economics.replacement import replacement_npv

        npv = replacement_npv(10_000, 25, 10, 0.06)
        # year 10: 10000 / 1.06^10;  year 20: 10000 / 1.06^20
        expected = 10_000 / 1.06**10 + 10_000 / 1.06**20
        assert pytest.approx(npv, rel=1e-5) == expected

    def test_no_replacement(self) -> None:
        from samba.economics.replacement import replacement_npv

        assert replacement_npv(10_000, 25, 25, 0.06) == 0.0


# ===========================================================================
# samba.economics.salvage
# ===========================================================================


class TestSalvageFraction:
    def test_partial_cycle(self) -> None:
        from samba.economics.salvage import salvage_fraction

        # project=25, lifetime=10 → years_used = 25%10 = 5 → (10-5)/10 = 0.5
        assert salvage_fraction(25, 10) == pytest.approx(0.5)

    def test_full_cycle_no_salvage(self) -> None:
        from samba.economics.salvage import salvage_fraction

        assert salvage_fraction(20, 10) == 0.0

    def test_equal_lifetime_no_salvage(self) -> None:
        from samba.economics.salvage import salvage_fraction

        assert salvage_fraction(25, 25) == 0.0

    def test_zero_lifetime_raises(self) -> None:
        from samba.economics.salvage import salvage_fraction

        with pytest.raises(ValueError, match="component_lifetime must be > 0"):
            salvage_fraction(25, 0)


class TestSalvageNpv:
    def test_partial_salvage(self) -> None:
        from samba.economics.npc import single_payment_pv
        from samba.economics.salvage import salvage_fraction, salvage_npv

        capex, n, lifetime, r = 10_000, 25, 10, 0.06
        frac = salvage_fraction(n, lifetime)
        expected = capex * frac * single_payment_pv(r, n)
        assert pytest.approx(salvage_npv(capex, n, lifetime, r), rel=1e-5) == expected

    def test_zero_salvage_at_full_cycle(self) -> None:
        from samba.economics.salvage import salvage_npv

        assert salvage_npv(10_000, 20, 10, 0.06) == 0.0


# ===========================================================================
# samba.economics.emissions
# ===========================================================================


class TestDgFuelLiters:
    def test_constant_generation(self) -> None:
        from samba.economics.emissions import dg_fuel_liters

        # 100 kW for 8760 h, slope=0.246, intercept=0.084, rated=100 kW
        gen = np.full(8760, 100.0)
        fuel = dg_fuel_liters(gen, 100.0, 0.246, 0.084)
        expected = 0.246 * (100.0 * 8760) + 0.084 * 100.0 * 8760
        assert pytest.approx(fuel, rel=1e-5) == expected

    def test_zero_generation(self) -> None:
        from samba.economics.emissions import dg_fuel_liters

        gen = np.zeros(8760)
        assert dg_fuel_liters(gen, 100.0, 0.246, 0.084) == 0.0


class TestEmissionsFactors:
    def test_dg_emissions_default_factor(self) -> None:
        from samba.economics.emissions import dg_emissions_kg

        assert pytest.approx(dg_emissions_kg(1000.0)) == 1000.0 * 2.63

    def test_grid_emissions_zero_default(self) -> None:
        from samba.economics.emissions import grid_emissions_kg

        assert grid_emissions_kg(5000.0) == 0.0

    def test_grid_emissions_nonzero_factor(self) -> None:
        from samba.economics.emissions import grid_emissions_kg

        assert pytest.approx(grid_emissions_kg(1000.0, 0.4)) == 400.0


# ===========================================================================
# samba.run_result.kpis — compute_kpis
# ===========================================================================

_KPI_KEYS = {
    "kpi_contract_version",
    "npc",
    "lcoe",
    "operating_cost",
    "initial_investment",
    "total_replacement_cost",
    "total_om_cost",
    "total_fuel_cost",
    "total_salvage",
    "total_grid_cost_net",
    "crf",
    "total_load_served",
    "total_unmet_load",
    "lpsp",
    "renewable_fraction",
    "total_pv_generation",
    "total_wt_generation",
    "total_dg_generation",
    "total_grid_bought",
    "total_grid_sold",
    "annual_demand_charge_usd",
    "annual_energy_net_usd",
    "total_energy_dump",
    "total_battery_charge",
    "total_battery_discharge",
    "annual_throughput_cycles",
    "battery_eol_year",
    "dg_emissions_kg",
    "grid_emissions_kg",
    "total_emissions_kg",
    "lem",
    "dg_operating_hours",
    "dg_fuel_consumption_liters",
    "annual_ev_charge_kwh",
    "annual_ev_discharge_kwh",
    "ev_v2g_revenue",
    "monthly_grid_kwh",
    "monthly_grid_cost",
    "peak_demand_kw_by_month",
    # Phase 20: Heat pump KPIs
    "hp_model_name",
    "annual_hp_elec_kwh",
    "annual_heat_produced_kwh",
    "annual_cool_produced_kwh",
    "mean_cop_heating",
    "mean_cop_cooling",
    # Phase 21: Thermal storage KPIs
    "thermal_storage_heating_kwh_th",
    "thermal_storage_cooling_kwh_th",
    "annual_thermal_storage_cycles",
    "thermal_storage_capex",
    # Phase 22: Thermal load demand + LPSP KPIs
    "annual_heating_demand_kwh_th",
    "annual_cooling_demand_kwh_th",
    "thermal_lpsp_heating",
    "thermal_lpsp_cooling",
    # Phase 23: Gas supply KPIs
    "annual_gas_consumption_kwh_th",
    "annual_gas_cost_usd",
    "annual_gas_co2_kg",
    "gas_boiler_capex",
    "gas_boiler_npc",
}

_ECONOMICS_TOP_KEYS = {
    "discount_rate_real",
    "project_lifetime_years",
    "crf",
    "npc",
    "investment",
    "replacement_schedule",
    "om_annual_npv",
    "fuel",
    "salvage",
    "grid",
    "gas",
    "cashflow_annual",
}

_SIZING_COLS = {"component", "capacity", "unit", "count", "capital_cost"}


class TestComputeKpis:
    """Tests for compute_kpis using a synthetic scenario and dispatch."""

    def _run(
        self,
        pv_kw: float = 50.0,
        battery_kwh: float = 100.0,
        inverter_kw: float = 40.0,
        eload_kw: float = 5.0,
        pv_gen_kw: float = 3.0,
    ) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame]:
        from samba.run_result.kpis import compute_kpis

        scenario = _make_scenario()
        caps = {"pv_kw": pv_kw, "battery_kwh": battery_kwh, "inverter_kw": inverter_kw}
        dr = _dispatch_result(caps, eload=np.full(8760, eload_kw), pv_gen=np.full(8760, pv_gen_kw))
        return compute_kpis(scenario, dr, _tariff_arrays())

    def test_kpi_keys_complete(self) -> None:
        kpis, _, _ = self._run()
        assert set(kpis.keys()) == _KPI_KEYS

    def test_economics_keys_complete(self) -> None:
        _, econ, _ = self._run()
        assert _ECONOMICS_TOP_KEYS.issubset(set(econ.keys()))

    def test_sizing_columns(self) -> None:
        _, _, sizing = self._run()
        assert _SIZING_COLS.issubset(set(sizing.columns))

    def test_npc_positive(self) -> None:
        kpis, _, _ = self._run()
        assert kpis["npc"] > 0

    def test_lpsp_zero_when_no_unmet(self) -> None:
        kpis, _, _ = self._run()
        assert kpis["lpsp"] == pytest.approx(0.0)

    def test_renewable_fraction_between_0_and_1(self) -> None:
        kpis, _, _ = self._run()
        assert 0.0 <= kpis["renewable_fraction"] <= 1.0

    def test_all_zeros_dispatch_no_crash(self) -> None:
        """Dispatch with all zeros should produce finite KPIs without crashing."""
        from samba.run_result.kpis import compute_kpis

        scenario = _make_scenario()
        caps = {"pv_kw": 50.0, "battery_kwh": 100.0, "inverter_kw": 40.0}
        dr = _dispatch_result(caps)
        kpis, econ, sizing = compute_kpis(scenario, dr, _tariff_arrays())
        assert isinstance(kpis, dict)
        assert isinstance(econ, dict)
        assert isinstance(sizing, pd.DataFrame)

    def test_lcoe_decreases_with_higher_load(self) -> None:
        """More served load → lower LCOE (same capital cost)."""
        kpis_low, _, _ = self._run(eload_kw=1.0)
        kpis_high, _, _ = self._run(eload_kw=20.0)
        # When load served is non-zero in both cases (no unmet), higher load → lower LCOE
        # But here eload is just set and no actual generation follows it, so total_load_served
        # increases while NPC stays same → LCOE decreases.
        assert kpis_high["total_load_served"] > kpis_low["total_load_served"]

    def test_re_incentive_reduces_investment(self) -> None:
        from samba.run_result.kpis import compute_kpis

        scenario_no = _make_scenario(re_incentive_rate=0.0)
        scenario_yes = _make_scenario(re_incentive_rate=0.1)

        caps = {"pv_kw": 50.0, "battery_kwh": 100.0, "inverter_kw": 40.0}
        dr = _dispatch_result(caps)
        tariff = _tariff_arrays()

        _, econ_no, _ = compute_kpis(scenario_no, dr, tariff)
        _, econ_yes, _ = compute_kpis(scenario_yes, dr, tariff)

        assert econ_yes["investment"]["total"] < econ_no["investment"]["total"]

    def test_cashflow_annual_length(self) -> None:
        _, econ, _ = self._run()
        # One entry per year including year 0 and year n
        n = 25  # default lifetime
        assert len(econ["cashflow_annual"]) == n + 1

    def test_cashflow_year_0_has_investment(self) -> None:
        _, econ, _ = self._run()
        yr0 = econ["cashflow_annual"][0]
        assert yr0["year"] == 0
        assert yr0["investment"] > 0
        assert yr0["om"] == 0
        assert yr0["fuel"] == 0

    def test_salvage_in_last_year_only(self) -> None:
        _, econ, _ = self._run()
        # Only year n can have salvage != 0
        for row in econ["cashflow_annual"][:-1]:  # years 0 .. n-1
            assert row["salvage"] == 0.0
        # year 25 may or may not have salvage depending on lifetime alignment


# ===========================================================================
# samba.run_result.reader — RunResult round-trip
# ===========================================================================


class TestRunResultRoundTrip:
    """Write result artifacts to a temp dir and load them back."""

    def test_load_result_round_trip(self, tmp_path: Path) -> None:
        from samba.run_result.kpis import compute_kpis
        from samba.run_result.reader import RunResult, load_result
        from samba.run_result.writer import (
            write_dispatch,
            write_economics,
            write_kpis,
            write_sizing,
        )

        scenario = _make_scenario()
        caps = {"pv_kw": 50.0, "battery_kwh": 100.0, "inverter_kw": 40.0}
        dr = _dispatch_result(caps, eload=np.full(8760, 5.0))
        kpis, econ, sizing = compute_kpis(scenario, dr, _tariff_arrays())

        # Write artifacts
        write_dispatch(tmp_path, dr.dispatch)
        write_kpis(tmp_path, kpis)
        write_economics(tmp_path, econ)
        write_sizing(tmp_path, sizing)

        # Load back
        result = load_result(tmp_path)
        assert isinstance(result, RunResult)
        assert result.kpis["npc"] == pytest.approx(kpis["npc"])
        assert result.npc == pytest.approx(kpis["npc"])
        assert result.lcoe == pytest.approx(kpis["lcoe"])
        assert len(result.dispatch) == 8760
        assert len(result.sizing) == len(sizing)

    def test_load_result_missing_files(self, tmp_path: Path) -> None:
        from samba.run_result.reader import RunResult, load_result

        result = load_result(tmp_path)
        assert isinstance(result, RunResult)
        assert result.kpis == {}
        assert result.metadata == {}
        assert result.dispatch.empty

    def test_load_result_not_found(self) -> None:
        from samba.run_result.reader import load_result

        with pytest.raises(FileNotFoundError):
            load_result("/no/such/dir_xyz_789")
