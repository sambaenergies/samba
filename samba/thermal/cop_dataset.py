# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Fit heat-pump COP curves from an empirical performance dataset.

This lets SAMBA replace its built-in physics-based (Carnot-fraction) COP model
with curves fitted to a user-supplied performance dataset -- for example the
public NEEP cold-climate ASHP listings, DOE ResStock / ComStock, or AHRI 210/240
rating points. **SAMBA ships no such dataset**; you provide the CSV and point a
scenario at it with ``heat_pump.cop_source: "dataset"`` and
``heat_pump.cop_dataset_path``.

Dataset format
--------------
A CSV with a header row and these columns (extra columns are ignored)::

    outdoor_temp_c,cop_heating,cop_cooling

- ``outdoor_temp_c`` (required): outdoor dry-bulb temperature [deg C].
- ``cop_heating`` (optional): measured/rated heating COP at that temperature.
- ``cop_cooling`` (optional): measured/rated cooling COP at that temperature.

Provide at least the column(s) for the mode(s) you model. A cell left blank in
``cop_heating`` / ``cop_cooling`` is simply skipped for that curve, so heating
and cooling rating points may appear on separate rows.

A least-squares polynomial (degree 2, automatically reduced when only 2 points
are available) is fitted to the points of each present column. The fitted curve
is evaluated per hour against the outdoor temperature and clipped to
``[COP_FLOOR, COP_CEILING]`` -- the same physical bounds the built-in model uses.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from samba.thermal.constants import COP_CEILING, COP_FLOOR

__all__ = ["COPCurves", "load_cop_dataset", "fit_cop_curves", "evaluate_curve"]

_MAX_DEGREE = 2


@dataclass(frozen=True)
class COPCurves:
    """Fitted COP-vs-outdoor-temperature polynomials.

    Coefficients follow the :func:`numpy.polyfit` convention (highest power
    first). ``None`` means the dataset contained no usable points for that mode.
    """

    heating: tuple[float, ...] | None
    cooling: tuple[float, ...] | None


def load_cop_dataset(
    path: str | Path,
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Parse a COP dataset CSV.

    Returns ``(temps_h, cops_h, temps_c, cops_c)`` -- the temperature/COP point
    pairs for heating and cooling respectively (each list aligned by index).

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the required ``outdoor_temp_c`` column is missing.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"COP dataset not found: {p}")

    temps_h: list[float] = []
    cops_h: list[float] = []
    temps_c: list[float] = []
    cops_c: list[float] = []

    with p.open(newline="", encoding="utf-8") as fh:
        # Skip provenance/comment lines (the fetch tool writes a "# ..." header).
        data_lines = [ln for ln in fh if not ln.lstrip().startswith("#")]
        reader = csv.DictReader(data_lines)
        fields = {name.strip() for name in (reader.fieldnames or [])}
        if "outdoor_temp_c" not in fields:
            raise ValueError(
                f"COP dataset '{p}' must have an 'outdoor_temp_c' column; got {sorted(fields)}"
            )
        has_h = "cop_heating" in fields
        has_c = "cop_cooling" in fields
        if not (has_h or has_c):
            raise ValueError(
                f"COP dataset '{p}' must have a 'cop_heating' and/or 'cop_cooling' column"
            )

        for row in reader:
            t_raw = (row.get("outdoor_temp_c") or "").strip()
            if not t_raw:
                continue
            t = float(t_raw)
            if has_h:
                h_raw = (row.get("cop_heating") or "").strip()
                if h_raw:
                    temps_h.append(t)
                    cops_h.append(float(h_raw))
            if has_c:
                c_raw = (row.get("cop_cooling") or "").strip()
                if c_raw:
                    temps_c.append(t)
                    cops_c.append(float(c_raw))

    return temps_h, cops_h, temps_c, cops_c


def _fit_one(temps: list[float], cops: list[float]) -> tuple[float, ...] | None:
    """Least-squares polynomial fit; ``None`` when there are too few points."""
    n = len(temps)
    if n < 2:
        return None
    degree = min(_MAX_DEGREE, n - 1)
    coeffs = np.polyfit(np.asarray(temps, dtype=float), np.asarray(cops, dtype=float), degree)
    return tuple(float(c) for c in coeffs)


def fit_cop_curves(path: str | Path) -> COPCurves:
    """Load *path* and least-squares fit a heating and/or cooling COP curve.

    Raises
    ------
    ValueError
        If neither a heating nor a cooling curve could be fitted (fewer than two
        usable points for every mode present in the file).
    """
    temps_h, cops_h, temps_c, cops_c = load_cop_dataset(path)
    heating = _fit_one(temps_h, cops_h)
    cooling = _fit_one(temps_c, cops_c)
    if heating is None and cooling is None:
        raise ValueError(
            f"COP dataset '{path}' has too few usable points to fit any curve "
            "(need at least two temperature/COP pairs for heating or cooling)."
        )
    return COPCurves(heating=heating, cooling=cooling)


def evaluate_curve(coeffs: tuple[float, ...], t_outdoor: np.ndarray) -> np.ndarray:
    """Evaluate a fitted curve over *t_outdoor* [deg C], clipped to physical bounds."""
    cop = np.polyval(np.asarray(coeffs, dtype=float), np.asarray(t_outdoor, dtype=float))
    return np.asarray(np.clip(cop, COP_FLOOR, COP_CEILING), dtype=float)
