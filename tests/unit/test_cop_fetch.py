# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for the COP dataset sourcing/normalisation tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from samba.thermal.cop_dataset import fit_cop_curves
from samba.thermal.cop_fetch import (
    NEEP_RATING_POINTS,
    build_cop_dataset,
    normalize_rating_points,
)

# A synthetic NEEP-like wide export: one row per model, COP columns per rating temp,
# plus an EER cooling column. Two models so the median aggregation is exercised.
_RAW = (
    "Brand,Model,COP @ 47F (Max),COP @ 17F (Max),COP @ 5F (Max),EER @ 82F,EER @ 95F\n"
    "Acme,H1,3.6,2.3,1.9,13.5,11.0\n"
    "Beta,H2,3.8,2.5,2.1,15.5,13.0\n"
)


def test_normalize_medians_across_models() -> None:
    rows = [
        {"COP @ 47F (Max)": "3.6", "COP @ 17F (Max)": "2.3", "EER @ 95F": "11.0"},
        {"COP @ 47F (Max)": "3.8", "COP @ 17F (Max)": "2.5", "EER @ 95F": "13.0"},
    ]
    out = normalize_rating_points(rows, NEEP_RATING_POINTS)
    by_temp = {r["outdoor_temp_c"]: r for r in out}
    # heating median at 47F (8.33C): median(3.6, 3.8) = 3.7
    assert by_temp[8.33]["cop_heating"] == pytest.approx(3.7)
    # cooling at 95F (35C): EER median(11,13)=12 -> COP = 12 / 3.412142 ≈ 3.517
    assert by_temp[35.0]["cop_cooling"] == pytest.approx(12.0 / 3.412142, abs=1e-3)
    assert by_temp[8.33]["cop_cooling"] == ""  # heating row has no cooling value


def test_build_from_file_writes_provenance_and_is_fittable(tmp_path: Path) -> None:
    raw = tmp_path / "neep_export.csv"
    raw.write_text(_RAW, encoding="utf-8")
    out = tmp_path / "curated.csv"

    written = build_cop_dataset(out_path=out, from_file=raw, source_label="Test source")
    text = written.read_text(encoding="utf-8")

    # Provenance header present and auditable.
    assert text.startswith("# SAMBA COP dataset curated from: Test source")
    assert "Raw SHA-256:" in text
    assert "Models aggregated: 2" in text
    assert "LICENSE:" in text

    # The curated output round-trips through the fitter (comment lines are skipped).
    curves = fit_cop_curves(written)
    assert curves.heating is not None
    assert curves.cooling is not None


def test_build_requires_exactly_one_source(tmp_path: Path) -> None:
    out = tmp_path / "curated.csv"
    with pytest.raises(ValueError, match="exactly one"):
        build_cop_dataset(out_path=out)
    with pytest.raises(ValueError, match="exactly one"):
        build_cop_dataset(out_path=out, from_file=Path("a"), url="http://x")


def test_build_errors_when_spec_matches_nothing(tmp_path: Path) -> None:
    raw = tmp_path / "raw.csv"
    raw.write_text("Brand,Model,Irrelevant\nAcme,H1,5\n", encoding="utf-8")
    out = tmp_path / "curated.csv"
    with pytest.raises(ValueError, match="No rating points matched"):
        build_cop_dataset(out_path=out, from_file=raw)
