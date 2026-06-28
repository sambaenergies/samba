# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for dataset-driven heat-pump COP fitting (cop_source='dataset')."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from samba.thermal.constants import COP_CEILING, COP_FLOOR
from samba.thermal.cop import build_cop_arrays
from samba.thermal.cop_dataset import (
    COPCurves,
    evaluate_curve,
    fit_cop_curves,
    load_cop_dataset,
)

_REFERENCE_CSV = (
    Path(__file__).resolve().parents[2] / "examples" / "content" / "cop_ashp_reference.csv"
)


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "cop.csv"
    p.write_text(text, encoding="utf-8")
    return p


class TestLoadAndFit:
    def test_load_splits_heating_and_cooling(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            "outdoor_temp_c,cop_heating,cop_cooling\n-8.3,2.4,\n8.3,3.7,\n35,,3.3\n",
        )
        th, ch, tc, cc = load_cop_dataset(p)
        assert th == [-8.3, 8.3]
        assert ch == [2.4, 3.7]
        assert tc == [35.0]
        assert cc == [3.3]

    def test_comment_lines_skipped(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            "# provenance header\n# more\noutdoor_temp_c,cop_heating\n0,3.0\n10,4.0\n",
        )
        th, ch, _, _ = load_cop_dataset(p)
        assert th == [0.0, 10.0]
        assert ch == [3.0, 4.0]

    def test_missing_temp_column_raises(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "cop_heating\n3.0\n")
        with pytest.raises(ValueError, match="outdoor_temp_c"):
            load_cop_dataset(p)

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_cop_dataset("/no/such/cop.csv")

    def test_fit_recovers_points(self, tmp_path: Path) -> None:
        p = _write(
            tmp_path,
            "outdoor_temp_c,cop_heating\n-15,2.0\n0,3.0\n15,4.5\n",
        )
        curves = fit_cop_curves(p)
        assert curves.heating is not None
        got = evaluate_curve(curves.heating, np.array([-15.0, 0.0, 15.0]))
        assert got == pytest.approx([2.0, 3.0, 4.5], abs=1e-6)

    def test_single_point_yields_no_curve(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "outdoor_temp_c,cop_heating,cop_cooling\n0,3.0,\n10,,4.0\n")
        # one heating point, one cooling point -> neither fittable
        with pytest.raises(ValueError, match="too few"):
            fit_cop_curves(p)

    def test_evaluate_clipped_to_bounds(self, tmp_path: Path) -> None:
        # A steep linear fit pushed far past the data range must stay bounded.
        p = _write(tmp_path, "outdoor_temp_c,cop_heating\n0,2.0\n10,6.0\n")
        curves = fit_cop_curves(p)
        assert curves.heating is not None
        got = evaluate_curve(curves.heating, np.array([-100.0, 100.0]))
        assert float(got.min()) >= COP_FLOOR
        assert float(got.max()) <= COP_CEILING + 1e-9


class TestReferenceDataset:
    def test_reference_csv_present_and_fittable(self) -> None:
        assert _REFERENCE_CSV.exists(), f"missing committed reference dataset: {_REFERENCE_CSV}"
        curves = fit_cop_curves(_REFERENCE_CSV)
        assert isinstance(curves, COPCurves)
        assert curves.heating is not None
        assert curves.cooling is not None

    def test_reference_curves_physically_ordered(self) -> None:
        curves = fit_cop_curves(_REFERENCE_CSV)
        assert curves.heating is not None and curves.cooling is not None
        # heating COP rises with outdoor temp; cooling COP falls.
        h = evaluate_curve(curves.heating, np.array([-15.0, 0.0, 10.0]))
        c = evaluate_curve(curves.cooling, np.array([27.0, 35.0, 45.0]))
        assert np.all(np.diff(h) > 0)
        assert np.all(np.diff(c) < 0)


class TestBuildCOPArraysDataset:
    def _hp(self, path: str, **kw: Any) -> Any:
        from samba.scenario.models import HeatPump

        defaults: dict[str, Any] = {
            "enabled": True,
            "mode": "both",
            "sizing": "catalog_auto",
            "cop_source": "dataset",
            "cop_dataset_path": path,
        }
        defaults.update(kw)
        return HeatPump(**defaults)

    def test_build_from_reference_dataset(self) -> None:
        hp = self._hp(str(_REFERENCE_CSV))
        t = np.linspace(-10.0, 35.0, 8760)
        arr = build_cop_arrays(hp, t, peak_heating_kw=5.0)
        assert arr.heating is not None and arr.cooling is not None
        assert arr.heating.shape == (8760,)
        assert float(arr.heating.min()) >= COP_FLOOR
        assert float(arr.cooling.max()) <= COP_CEILING + 1e-9

    def test_relative_path_resolved_against_base_dir(self) -> None:
        hp = self._hp("cop_ashp_reference.csv")
        t = np.zeros(8760) + 5.0
        arr = build_cop_arrays(hp, t, base_dir=_REFERENCE_CSV.parent)
        assert arr.heating is not None

    def test_missing_required_mode_column_raises(self, tmp_path: Path) -> None:
        p = _write(tmp_path, "outdoor_temp_c,cop_heating\n-8.3,2.4\n8.3,3.7\n0,3.0\n")
        hp = self._hp(str(p), mode="cooling_only")
        with pytest.raises(ValueError, match="cooling"):
            build_cop_arrays(hp, np.zeros(10) + 30.0)

    def test_validator_requires_dataset_path(self) -> None:
        from samba.scenario.models import HeatPump

        with pytest.raises(ValueError, match="cop_dataset_path"):
            HeatPump(enabled=True, cop_source="dataset")
