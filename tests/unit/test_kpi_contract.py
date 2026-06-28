# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Tests that kpis.json output embeds the KPI contract version."""

from __future__ import annotations

import pytest


class TestKpiContractVersion:
    """The ``kpi_contract_version`` key is present and matches the constant."""

    def test_constant_is_string(self) -> None:
        from samba._kpi_contract import KPI_CONTRACT_VERSION

        assert isinstance(KPI_CONTRACT_VERSION, str)
        assert KPI_CONTRACT_VERSION  # non-empty

    def test_constant_value(self) -> None:
        from samba._kpi_contract import KPI_CONTRACT_VERSION

        assert KPI_CONTRACT_VERSION == "2.1"

    def test_kpis_output_contains_version_key(self, minimal_kpis: dict) -> None:  # type: ignore[type-arg]
        """compute_kpis output must contain 'kpi_contract_version'."""
        assert "kpi_contract_version" in minimal_kpis

    def test_kpis_version_matches_constant(self, minimal_kpis: dict) -> None:  # type: ignore[type-arg]
        from samba._kpi_contract import KPI_CONTRACT_VERSION

        assert minimal_kpis["kpi_contract_version"] == KPI_CONTRACT_VERSION

    def test_kpis_version_is_first_key(self, minimal_kpis: dict) -> None:  # type: ignore[type-arg]
        """Contract version should be the first key for easy human inspection."""
        assert next(iter(minimal_kpis)) == "kpi_contract_version"


# ---------------------------------------------------------------------------
# Fixture — build a minimal kpis dict via compute_kpis
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_kpis(minimal_scenario_dict: dict) -> dict:  # type: ignore[type-arg]
    """Return the kpis portion of a compute_kpis() call on a minimal scenario."""
    import numpy as np

    from samba.run_result.kpis import compute_kpis
    from samba.scenario.models import Scenario
    from samba.solver.extract import DispatchResult
    from samba.tariff.resolver import TariffArrays

    scenario = Scenario.model_validate(minimal_scenario_dict)

    n = 8760
    zeros = np.zeros(n)
    small = np.full(n, 1.0)  # 1 kW load so totals are non-zero

    dispatch_df = __import__("pandas").DataFrame(
        {
            "eload": small,
            "unmet_load": zeros,
            "pv_gen": small,
            "wt_gen": zeros,
            "dg_gen": zeros,
            "grid_buy": zeros,
            "grid_sell": zeros,
            "energy_dump": zeros,
            "batt_charge": zeros,
            "batt_discharge": zeros,
            "battery_soc_kwh": zeros,
        }
    )
    caps: dict[str, float] = {
        "pv_kw": 1.0,
        "battery_kwh": 0.0,
        "inverter_kw": 1.0,
        "wt_kw": 0.0,
        "dg_kw": 0.0,
        "grid_kw": 0.0,
    }
    dr = DispatchResult(dispatch=dispatch_df, capacities=caps)
    ta = TariffArrays(cbuy=zeros, csell=zeros, service_charge=np.zeros(12))

    kpis, _economics, _sizing = compute_kpis(scenario, dr, ta)
    return kpis


@pytest.fixture()
def minimal_scenario_dict() -> dict:  # type: ignore[type-arg]
    """Minimal valid scenario dict for KPI contract tests."""
    return {
        "schema_version": "1.0",
        "project": {
            "name": "kpi-contract-test",
            "lifetime_years": 20,
            "discount_rate_nominal": 0.05,
            "inflation_rate": 0.02,
        },
        "location": {"latitude": 51.5, "longitude": -0.1, "timezone": "Europe/London"},
        "weather": {"source": "csv", "csv_path": "dummy.csv"},
        "load": {"source": "generic_annual_total", "annual_kwh": 8760.0},
        "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.15}},
        "components": {
            "inverter": {"capex_per_kw": 200.0, "capacity_kw": 1.0},
            "pv": {"capex_per_kw": 1000.0, "capacity_kw": 1.0},
        },
        "objective": {"type": "cost"},
    }
