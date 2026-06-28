# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""SAMBA - Systems Advisor for Microgrids & Building Analysis.

The top-level :func:'run' convenience function executes the full solve-and-
post-process pipeline in a single call::

    import numpy as np
    import samba

    result = samba.run(
        scenario,
        load_kw=my_load_array,
        pv_per_kwp=my_pv_profile,
        output_dir="outputs/",
    )
    print(result.npc, result.lcoe)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from samba._version import __version__

if TYPE_CHECKING:
    import numpy as np

    from samba.run_result.reader import RunResult
    from samba.scenario.models import Scenario
    from samba.solver.runner import SolverConfig
    from samba.tariff.resolver import TariffArrays
    from samba.weather import WeatherData

__all__ = ["__version__", "run"]


def run(
    scenario_or_path: Scenario | Path | str,
    *,
    load_kw: np.ndarray,
    output_dir: Path | str | None = None,
    config: SolverConfig | None = None,
    pv_per_kwp: np.ndarray | None = None,
    tariff_arrays: TariffArrays | None = None,
    wind_power_kw: np.ndarray | None = None,
    weather: WeatherData | None = None,
    scenario_dir: Path | str | None = None,
) -> RunResult:
    """Run the full SAMBA pipeline and return a :class:'~samba.run_result.reader.RunResult'."""
    # Deferred by design (audit M8): importing the pipeline pulls in the heavy
    # oemof-solph / pyomo / pandas stack. Keeping it lazy means ``import samba``
    # and ``samba --version`` stay fast for callers that don't run a solve.
    # (There is no circular-import dependency; this is purely an import-cost choice.)
    from samba._pipeline import run_pipeline

    return run_pipeline(
        scenario_or_path,
        load_kw=load_kw,
        output_dir=output_dir,
        config=config,
        pv_per_kwp=pv_per_kwp,
        tariff_arrays=tariff_arrays,
        wind_power_kw=wind_power_kw,
        weather=weather,
        scenario_dir=scenario_dir,
    )
