# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Public API for the ``samba.run_result`` package."""

from samba.run_result.kpis import compute_kpis
from samba.run_result.reader import RunResult, load_result
from samba.run_result.writer import (
    build_metadata,
    ensure_run_dir,
    write_dispatch,
    write_economics,
    write_kpis,
    write_metadata,
    write_scenario,
    write_sizing,
    write_tariff,
)

__all__ = [
    "compute_kpis",
    "build_metadata",
    "ensure_run_dir",
    "load_result",
    "RunResult",
    "write_dispatch",
    "write_economics",
    "write_kpis",
    "write_metadata",
    "write_scenario",
    "write_sizing",
    "write_tariff",
]
