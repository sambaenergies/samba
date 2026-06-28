# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Single-source-of-truth for the KPI output contract version.

This constant is embedded as ''"kpi_contract_version"'' in every ''kpis.json''
artefact produced by :func:'samba.run_result.kpis.compute_kpis'.  Downstream
tooling (dashboards, CI golden comparisons) should read this field to guard
against schema drift.

Version history
---------------
''"2.0"''
    Initial versioned contract.  All 28 core KPI fields defined in
    ''docs/developer/results-contract.md'' plus ''monthly_grid_kwh'' and
    ''monthly_grid_cost'' breakdowns.
''"2.1"''
    Additive (v4 Phases 25/27): ''annual_demand_charge_usd'', ''annual_energy_net_usd'',
    ''peak_demand_kw_by_month'' (Phase 25); ''annual_throughput_cycles'',
    ''battery_eol_year'' (Phase 27 battery degradation).  Backwards-compatible —
    existing fields unchanged.
"""

from __future__ import annotations

__all__ = ["KPI_CONTRACT_VERSION"]

#: Bumped whenever the ''kpis.json'' schema changes (minor = additive).
KPI_CONTRACT_VERSION: str = "2.1"
