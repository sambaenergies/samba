# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Golden scenario benchmark tests.

Each golden test:

1. Loads a ``scenario.yaml`` file from one of the ``g0N_*/`` subdirectories.
2. Resolves the load, weather, and wind arrays via the data pipeline.
3. Calls :func:`samba.run` to solve the full optimisation.
4. Compares the SAMBA KPIs against ``reference.json`` within the agreed
   tolerances.

Test organisation
-----------------
* **Fast structural tests** (no solver, always run):
  - ``test_scenario_yaml_loads``   — YAML parses and validates without error.
  - ``test_reference_json_valid``  — reference.json has required keys.
  - ``test_assert_tolerance_unit`` — unit tests for the tolerance helper.

* **Benchmark tests** (``@pytest.mark.benchmark``, slow — require solver):
  - ``test_golden_kpis``  — full end-to-end solve + KPI comparison.

Run commands
------------
::

    pytest tests/goldens/ -v                     # all golden tests (schema + benchmark)
    pytest tests/goldens/ -m "not benchmark"     # schema tests only (fast)
    pytest tests/goldens/ -m benchmark -v        # benchmark tests only
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import samba
from samba.input_resolver import resolve_arrays
from samba.scenario import ScenarioValidationError

from .conftest import (
    assert_within_tolerance,
    golden_scenario_dirs,
    load_golden_scenario,
    load_reference,
)

# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

_REQUIRED_REFERENCE_KEYS = ("scenario", "source", "kpis", "tolerances")
_REQUIRED_KPI_KEYS = (
    "npc",
    "lcoe",
    "pv_kw",
    "battery_kwh",
    "inverter_kw",
    "annual_pv_kwh",
    "renewable_fraction",
    "annual_diesel_l",
)


def _extract_samba_kpis(result: samba.run_result.reader.RunResult) -> dict[str, float]:  # type: ignore[name-defined]
    """Map a :class:`~samba.run_result.reader.RunResult` into the flat KPI dict
    expected by :func:`~conftest.assert_within_tolerance`.

    Parameters
    ----------
    result:
        Return value of :func:`samba.run`.

    Returns
    -------
    dict[str, float]
        Flat dict with keys matching ``reference.json`` ``"kpis"`` section.
    """
    kpis: dict[str, float] = {}

    # Direct KPI fields
    kpis["npc"] = float(result.kpis.get("npc", 0.0))
    kpis["lcoe"] = float(result.kpis.get("lcoe", 0.0))
    kpis["annual_pv_kwh"] = float(result.kpis.get("total_pv_generation", 0.0))
    kpis["renewable_fraction"] = float(result.kpis.get("renewable_fraction", 0.0))
    kpis["annual_diesel_l"] = float(result.kpis.get("dg_fuel_consumption_liters", 0.0))

    # v2 scalar KPI fields (present in v2 golden references; 0.0 for v1 scenarios)
    kpis["total_emissions_kg"] = float(result.kpis.get("total_emissions_kg", 0.0))
    kpis["total_grid_bought"] = float(result.kpis.get("total_grid_bought", 0.0))
    kpis["total_grid_cost_net"] = float(result.kpis.get("total_grid_cost_net", 0.0))
    kpis["annual_ev_charge_kwh"] = float(result.kpis.get("annual_ev_charge_kwh", 0.0))
    kpis["annual_ev_discharge_kwh"] = float(result.kpis.get("annual_ev_discharge_kwh", 0.0))
    kpis["ev_v2g_revenue"] = float(result.kpis.get("ev_v2g_revenue", 0.0))
    kpis["lpsp"] = float(result.kpis.get("lpsp", 0.0))
    kpis["dg_operating_hours"] = float(result.kpis.get("dg_operating_hours", 0))

    # v4 scalar KPI fields (present in v4 golden references; 0.0 for earlier scenarios)
    kpis["annual_demand_charge_usd"] = float(result.kpis.get("annual_demand_charge_usd", 0.0))
    kpis["annual_energy_net_usd"] = float(result.kpis.get("annual_energy_net_usd", 0.0))
    kpis["annual_throughput_cycles"] = float(result.kpis.get("annual_throughput_cycles", 0.0))
    kpis["battery_eol_year"] = float(result.kpis.get("battery_eol_year", 0))

    # v3 thermal KPI fields (present in v3 golden references; 0.0 for v1/v2 scenarios)
    kpis["annual_heat_produced_kwh"] = float(result.kpis.get("annual_heat_produced_kwh", 0.0))
    kpis["annual_cool_produced_kwh"] = float(result.kpis.get("annual_cool_produced_kwh", 0.0))
    kpis["mean_cop_heating"] = float(result.kpis.get("mean_cop_heating", 0.0))
    kpis["mean_cop_cooling"] = float(result.kpis.get("mean_cop_cooling", 0.0))
    kpis["annual_heating_demand_kwh_th"] = float(
        result.kpis.get("annual_heating_demand_kwh_th", 0.0)
    )
    kpis["annual_cooling_demand_kwh_th"] = float(
        result.kpis.get("annual_cooling_demand_kwh_th", 0.0)
    )
    kpis["annual_hp_elec_kwh"] = float(result.kpis.get("annual_hp_elec_kwh", 0.0))
    kpis["thermal_storage_capex"] = float(result.kpis.get("thermal_storage_capex", 0.0))
    kpis["annual_thermal_storage_cycles"] = float(
        result.kpis.get("annual_thermal_storage_cycles", 0.0)
    )
    kpis["annual_gas_consumption_kwh_th"] = float(
        result.kpis.get("annual_gas_consumption_kwh_th", 0.0)
    )
    kpis["annual_gas_cost_usd"] = float(result.kpis.get("annual_gas_cost_usd", 0.0))
    kpis["annual_gas_co2_kg"] = float(result.kpis.get("annual_gas_co2_kg", 0.0))
    kpis["gas_boiler_npc"] = float(result.kpis.get("gas_boiler_npc", 0.0))
    kpis["gas_boiler_capex"] = float(result.kpis.get("gas_boiler_capex", 0.0))

    # Sizing from the sizing DataFrame
    sizing = result.sizing
    if sizing is not None and not sizing.empty:
        pv_rows = sizing[sizing["component"] == "pv"]
        bat_rows = sizing[sizing["component"] == "battery_energy"]
        inv_rows = sizing[sizing["component"] == "inverter"]

        kpis["pv_kw"] = float(pv_rows["capacity"].sum()) if not pv_rows.empty else 0.0
        kpis["battery_kwh"] = float(bat_rows["capacity"].sum()) if not bat_rows.empty else 0.0
        kpis["inverter_kw"] = float(inv_rows["capacity"].sum()) if not inv_rows.empty else 0.0
    else:
        kpis["pv_kw"] = 0.0
        kpis["battery_kwh"] = 0.0
        kpis["inverter_kw"] = 0.0

    return kpis


# ---------------------------------------------------------------------------
# Fast structural tests — no solver required
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario_dir",
    golden_scenario_dirs(),
    ids=lambda p: p.name,
)
def test_scenario_yaml_loads(scenario_dir: Path) -> None:
    """scenario.yaml parses and validates without ScenarioValidationError."""
    try:
        scenario = load_golden_scenario(scenario_dir)
    except ScenarioValidationError as exc:
        pytest.fail(f"{scenario_dir.name}/scenario.yaml failed validation: {exc}")
    assert scenario is not None


@pytest.mark.parametrize(
    "scenario_dir",
    golden_scenario_dirs(),
    ids=lambda p: p.name,
)
def test_reference_json_valid(scenario_dir: Path) -> None:
    """reference.json exists, is valid JSON, and has required top-level keys."""
    ref = load_reference(scenario_dir)

    # Top-level keys
    for key in _REQUIRED_REFERENCE_KEYS:
        assert key in ref, f"{scenario_dir.name}/reference.json missing required key: {key!r}"

    # KPI keys
    for key in _REQUIRED_KPI_KEYS:
        assert key in ref["kpis"], f"{scenario_dir.name}/reference.json missing kpi: {key!r}"

    # Tolerance entries exist for every KPI
    for key in ref["kpis"]:
        assert key in ref["tolerances"], (
            f"{scenario_dir.name}/reference.json: kpi {key!r} has no matching tolerance"
        )

    # Tolerance types are valid
    for kpi_name, tol_spec in ref["tolerances"].items():
        assert "type" in tol_spec, (
            f"{scenario_dir.name}/reference.json: tolerance for {kpi_name!r} missing 'type'"
        )
        assert tol_spec["type"] in ("relative", "absolute"), (
            f"{scenario_dir.name}/reference.json: invalid tolerance type {tol_spec['type']!r}"
        )
        assert "value" in tol_spec, (
            f"{scenario_dir.name}/reference.json: tolerance for {kpi_name!r} missing 'value'"
        )

    # Two-tier KPI contract (audit L5): "kpis" holds scalars only (each is
    # tolerance-checked); list-valued KPIs (e.g. monthly_grid_kwh) live under
    # the optional "series_kpis" tier so they don't break tolerance validation.
    for kpi_name, kpi_value in ref["kpis"].items():
        assert isinstance(kpi_value, (int, float)) and not isinstance(kpi_value, bool), (
            f"{scenario_dir.name}/reference.json: kpi {kpi_name!r} must be a scalar; "
            "put list-valued KPIs under the 'series_kpis' key"
        )
    for series_name, series_value in ref.get("series_kpis", {}).items():
        assert isinstance(series_value, list), (
            f"{scenario_dir.name}/reference.json: series_kpis {series_name!r} must be a list"
        )


# ---------------------------------------------------------------------------
# Unit tests for the tolerance helper
# ---------------------------------------------------------------------------


class TestAssertWithinTolerance:
    """Unit tests for :func:`~conftest.assert_within_tolerance`."""

    def _ref(
        self,
        kpi_value: float,
        tol_type: str,
        tol_value: float,
    ) -> dict[str, Any]:
        return {
            "kpis": {"test_kpi": kpi_value},
            "tolerances": {
                "test_kpi": {"type": tol_type, "value": tol_value},
            },
        }

    def test_exact_match_passes(self) -> None:
        """Perfect match always passes."""
        assert_within_tolerance({"test_kpi": 100.0}, self._ref(100.0, "relative", 0.1))

    def test_relative_within_tolerance_passes(self) -> None:
        """9% deviation passes within ±10% relative tolerance."""
        assert_within_tolerance({"test_kpi": 109.0}, self._ref(100.0, "relative", 0.10))

    def test_relative_exactly_at_boundary_passes(self) -> None:
        """10% deviation is within ±10% (edge case — boundary is inclusive)."""
        assert_within_tolerance({"test_kpi": 110.0}, self._ref(100.0, "relative", 0.10))

    def test_relative_over_tolerance_fails(self) -> None:
        """11% deviation fails ±10% relative tolerance."""
        with pytest.raises(AssertionError, match="test_kpi"):
            assert_within_tolerance({"test_kpi": 111.0}, self._ref(100.0, "relative", 0.10))

    def test_absolute_within_tolerance_passes(self) -> None:
        """0.04 absolute deviation passes ±0.05 absolute tolerance."""
        assert_within_tolerance(
            {"test_kpi": 0.94},
            self._ref(0.90, "absolute", 0.05),
        )

    def test_absolute_over_tolerance_fails(self) -> None:
        """0.06 absolute deviation fails ±0.05 absolute tolerance."""
        with pytest.raises(AssertionError, match="test_kpi"):
            assert_within_tolerance(
                {"test_kpi": 0.96},
                self._ref(0.90, "absolute", 0.05),
            )

    def test_zero_ref_relative_treated_as_absolute(self) -> None:
        """Relative tolerance with ref=0 falls back to absolute comparison."""
        assert_within_tolerance({"test_kpi": 0.0}, self._ref(0.0, "relative", 0.1))

    def test_missing_kpi_in_samba_fails(self) -> None:
        """Missing KPI in SAMBA result raises AssertionError."""
        with pytest.raises(AssertionError, match="SAMBA result missing"):
            assert_within_tolerance({}, self._ref(100.0, "relative", 0.10))

    def test_multiple_kpis_all_pass(self) -> None:
        """Multiple KPIs all within tolerance passes."""
        reference = {
            "kpis": {"npc": 40000.0, "lcoe": 0.12, "pv_kw": 11.56},
            "tolerances": {
                "npc": {"type": "relative", "value": 0.10},
                "lcoe": {"type": "relative", "value": 0.10},
                "pv_kw": {"type": "relative", "value": 0.20},
            },
        }
        assert_within_tolerance(
            {"npc": 42000.0, "lcoe": 0.13, "pv_kw": 12.0},
            reference,
        )

    def test_multiple_kpis_one_fails_reports_all_failures(self) -> None:
        """When multiple KPIs fail, all failures are reported together."""
        reference = {
            "kpis": {"npc": 40000.0, "lcoe": 0.12},
            "tolerances": {
                "npc": {"type": "relative", "value": 0.05},
                "lcoe": {"type": "relative", "value": 0.05},
            },
        }
        with pytest.raises(AssertionError) as exc_info:
            assert_within_tolerance(
                {"npc": 50000.0, "lcoe": 0.20},
                reference,
            )
        msg = str(exc_info.value)
        assert "npc" in msg
        assert "lcoe" in msg


# ---------------------------------------------------------------------------
# Benchmark tests — full end-to-end solve (slow, requires solver)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
@pytest.mark.slow
@pytest.mark.parametrize(
    "scenario_dir",
    golden_scenario_dirs(),
    ids=lambda p: p.name,
)
def test_golden_kpis(scenario_dir: Path) -> None:
    """End-to-end golden scenario: solve with SAMBA and compare KPIs to reference.

    Tagged :attr:`pytest.mark.benchmark` — excluded from the regular fast
    test suite.  Run explicitly with::

        pytest tests/goldens/ -m benchmark -v

    For each golden scenario:

    1. Loads ``scenario.yaml`` and ``reference.json``.
    2. Resolves load / weather / wind arrays via :func:`~samba.input_resolver.resolve_arrays`.
    3. Calls :func:`samba.run` to solve the LP.
    4. Asserts that all KPIs are within the agreed tolerances via
       :func:`~conftest.assert_within_tolerance`.
    """
    scenario = load_golden_scenario(scenario_dir)
    reference = load_reference(scenario_dir)

    # Resolve data arrays using the scenario.yaml location as base_dir
    load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scenario, scenario_dir)

    # Solve — no output_dir to avoid writing files during tests.
    # Pass scenario_dir so thermal CSV paths and HP weather auto-loading work.
    result = samba.run(
        scenario,
        load_kw=load_kw,
        pv_per_kwp=pv_per_kwp,
        wind_power_kw=wind_power_kw,
        scenario_dir=scenario_dir,
        output_dir=None,
    )

    # Extract SAMBA KPIs in reference.json format
    samba_kpis = _extract_samba_kpis(result)

    # Log values for debugging
    print(f"\n{'Scenario':>20}: {scenario_dir.name}")
    print(f"{'KPI':<25} {'SAMBA':>12} {'Reference':>12}")
    print("-" * 52)
    for kpi_name in _REQUIRED_KPI_KEYS:
        samba_val = samba_kpis.get(kpi_name, float("nan"))
        ref_val = reference["kpis"].get(kpi_name, float("nan"))
        print(f"  {kpi_name:<23} {samba_val:>12.4f} {ref_val:>12.4f}")

    # Assert KPI tolerances
    assert_within_tolerance(samba_kpis, reference)
