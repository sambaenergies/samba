# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Regression: the dataset-COP example stays a valid, dataset-fitted demo.

``examples/grid_pv_heat_pump_dataset.yaml`` demonstrates the opt-in
``cop_source: "dataset"`` path using SAMBA's committed, license-clean
representative reference CSV. This locks that example as a working fixture and
verifies the fitted COP curves are physically sane and genuinely distinct from
the physics (Carnot-fraction) default that ships as the catalog COP.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from samba.scenario import load_scenario
from samba.thermal.constants import COP_CEILING, COP_FLOOR
from samba.thermal.cop import build_cop_arrays, compute_heating_cop

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
_EXAMPLE = _EXAMPLES / "grid_pv_heat_pump_dataset.yaml"
_REFERENCE_CSV = _EXAMPLES / "content" / "cop_ashp_reference.csv"


def test_example_loads_and_opts_into_dataset_cop() -> None:
    scenario = load_scenario(_EXAMPLE)
    hp = scenario.components.heat_pump
    assert hp is not None
    assert hp.cop_source == "dataset"
    assert hp.cop_dataset_path == "content/cop_ashp_reference.csv"
    # the configured relative path resolves to the committed representative dataset
    resolved = (_EXAMPLE.parent / hp.cop_dataset_path).resolve()
    assert resolved == _REFERENCE_CSV.resolve()
    assert resolved.exists()


def test_example_cop_is_dataset_fitted_not_physics() -> None:
    scenario = load_scenario(_EXAMPLE)
    hp = scenario.components.heat_pump
    assert hp is not None

    t_outdoor = np.linspace(-10.0, 35.0, 8760)
    arr = build_cop_arrays(
        hp,
        t_outdoor,
        peak_heating_kw=8.0,
        peak_cooling_kw=4.0,
        base_dir=_EXAMPLE.parent,
    )

    assert arr.heating is not None and arr.cooling is not None
    assert arr.heating.shape == (8760,) and arr.cooling.shape == (8760,)
    assert np.isfinite(arr.heating).all() and np.isfinite(arr.cooling).all()
    assert float(arr.heating.min()) >= COP_FLOOR
    assert float(arr.cooling.max()) <= COP_CEILING + 1e-9

    # The dataset fit must differ from the physics default for the same temps.
    physics_heating = compute_heating_cop(t_outdoor)
    assert not np.allclose(arr.heating, physics_heating)

    # Heating COP rises with outdoor temperature; cooling falls.
    cold = build_cop_arrays(
        hp, np.full(8760, -10.0), peak_heating_kw=8.0, peak_cooling_kw=4.0, base_dir=_EXAMPLE.parent
    )
    warm = build_cop_arrays(
        hp, np.full(8760, 10.0), peak_heating_kw=8.0, peak_cooling_kw=4.0, base_dir=_EXAMPLE.parent
    )
    assert cold.heating is not None and warm.heating is not None
    assert float(warm.heating[0]) > float(cold.heating[0])

    mild = build_cop_arrays(
        hp, np.full(8760, 28.0), peak_heating_kw=8.0, peak_cooling_kw=4.0, base_dir=_EXAMPLE.parent
    )
    hot = build_cop_arrays(
        hp, np.full(8760, 40.0), peak_heating_kw=8.0, peak_cooling_kw=4.0, base_dir=_EXAMPLE.parent
    )
    assert mild.cooling is not None and hot.cooling is not None
    assert float(mild.cooling[0]) > float(hot.cooling[0])
