# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Reproducibly source a heat-pump COP dataset from a public listing.

This is the acquisition half of the data-driven COP feature (the fitting half is
in :mod:`samba.thermal.cop_dataset`). It mirrors the ``samba fetch-weather``
pattern: pull from an authoritative public source, normalise to SAMBA's
``outdoor_temp_c,cop_heating,cop_cooling`` schema, and write a curated CSV with a
provenance header (source, retrieval date, raw checksum, model count). The solver
never fetches; it only reads the curated CSV.

Recommended source: the **NEEP cold-climate ASHP list**, which publishes rated COP
at the AHRI 210/240 outdoor temperatures (47 / 17 / 5 degF) per model. Its export
is *wide* (one row per model, a COP column per rating temperature), so we melt it
to long form and take the per-temperature **median** across models to get a
representative curve.

.. important::
    **Licensing — fetched data is LOCAL-ONLY.** SAMBA ships no third-party
    performance data and the default catalog COP is the license-clean
    first-principles physics model. NEEP's terms of use are not clearly
    redistribution-permissive, so a fetched curated CSV is for your own local use:
    it is written to a git-ignored path by default and **must not be committed to
    a repository or redistributed** unless you have confirmed the source grants
    those rights. The provenance header records the source so that decision is
    auditable. (The committed ``examples/content/cop_ashp_reference.csv`` is a
    separate, deliberately license-clean *representative* dataset — not fetched
    third-party data.)

    **Column names** in ``NEEP_RATING_POINTS`` are best-effort and the NEEP export
    format changes over time — confirm them against a current export (use
    ``--from-file`` on a downloaded copy) and adjust the spec if needed.
"""

from __future__ import annotations

import csv
import hashlib
import statistics
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "RatingPoint",
    "NEEP_RATING_POINTS",
    "normalize_rating_points",
    "fetch_url",
    "build_cop_dataset",
]

_BTU_PER_WH = 3.412142  # EER [BTU/Wh] -> COP [W/W] divisor


@dataclass(frozen=True)
class RatingPoint:
    """Maps one source column to a (mode, outdoor temperature) COP rating point.

    ``unit`` is ``"cop"`` (dimensionless) or ``"eer"`` (BTU/Wh, converted to COP).
    """

    column: str
    mode: str  # "heating" or "cooling"
    outdoor_temp_c: float
    unit: str = "cop"


# Best-effort NEEP cold-climate ASHP export mapping. CONFIRM against a current
# export — column names and available rating points change between revisions.
NEEP_RATING_POINTS: list[RatingPoint] = [
    RatingPoint("COP @ 47F (Max)", "heating", 8.33, "cop"),
    RatingPoint("COP @ 17F (Max)", "heating", -8.33, "cop"),
    RatingPoint("COP @ 5F (Max)", "heating", -15.0, "cop"),
    # Two cooling points are needed to fit a cooling curve; 82F + 95F are the
    # AHRI part-/full-load conditions. If the export carries only one, the
    # cooling curve is simply not fitted (heating still works).
    RatingPoint("EER @ 82F", "cooling", 27.78, "eer"),
    RatingPoint("EER @ 95F", "cooling", 35.0, "eer"),
]


def _to_cop(value: float, unit: str) -> float:
    if unit == "cop":
        return value
    if unit == "eer":
        return value / _BTU_PER_WH
    raise ValueError(f"Unknown rating unit {unit!r} (expected 'cop' or 'eer')")


def normalize_rating_points(
    rows: Iterable[dict[str, str]],
    spec: list[RatingPoint] | None = None,
) -> list[dict[str, float | str]]:
    """Melt a wide per-model export to SAMBA's long COP schema (median per point).

    Returns rows of ``{"outdoor_temp_c", "cop_heating", "cop_cooling"}`` sorted by
    temperature, one row per rating temperature that had at least one model value.
    """
    if spec is None:
        spec = NEEP_RATING_POINTS
    # (mode, temp) -> list of COP values across models
    buckets: dict[tuple[str, float], list[float]] = {}
    for row in rows:
        for rp in spec:
            raw = (row.get(rp.column) or "").strip()
            if not raw:
                continue
            try:
                cop = _to_cop(float(raw), rp.unit)
            except ValueError:
                continue
            if cop > 0:
                buckets.setdefault((rp.mode, rp.outdoor_temp_c), []).append(cop)

    # temp -> {heating: median, cooling: median}
    by_temp: dict[float, dict[str, float]] = {}
    for (mode, temp), vals in buckets.items():
        by_temp.setdefault(temp, {})[mode] = round(statistics.median(vals), 4)

    out: list[dict[str, float | str]] = []
    for temp in sorted(by_temp):
        modes = by_temp[temp]
        out.append(
            {
                "outdoor_temp_c": temp,
                "cop_heating": modes.get("heating", ""),
                "cop_cooling": modes.get("cooling", ""),
            }
        )
    return out


def fetch_url(url: str, dest: str | Path, timeout: float = 60.0) -> Path:
    """Download *url* to *dest* and return the path. Thin wrapper over urllib.

    Only ``http(s)`` URLs are accepted (no ``file://`` / other schemes), so a
    stray or malicious URL can't read local files via this helper.
    """
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError(f"only http(s) URLs are supported for fetch, got: {url!r}")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (scheme checked above)
        dest.write_bytes(resp.read())
    return dest


def _read_rows(path: str | Path) -> tuple[list[dict[str, str]], str]:
    """Return (parsed rows, sha256 hex) of a raw export CSV."""
    raw = Path(path).read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(text.splitlines()))
    return rows, checksum


def build_cop_dataset(
    *,
    out_path: str | Path,
    from_file: str | Path | None = None,
    url: str | None = None,
    spec: list[RatingPoint] | None = None,
    source_label: str = "NEEP cold-climate ASHP list",
) -> Path:
    """Source a raw export, normalise it, and write a curated COP dataset CSV.

    Exactly one of *from_file* / *url* must be given. The output carries a
    provenance header (source, retrieval date, raw checksum, model count) and a
    licensing reminder.
    """
    if (from_file is None) == (url is None):
        raise ValueError("provide exactly one of from_file= or url=")

    out_path = Path(out_path)
    if url is not None:
        raw_path = out_path.with_suffix(".raw.csv")
        fetch_url(url, raw_path)
        origin = url
    else:
        raw_path = Path(from_file)  # type: ignore[arg-type]
        origin = str(raw_path)

    rows, checksum = _read_rows(raw_path)
    curated = normalize_rating_points(rows, spec)
    if not curated:
        raise ValueError(
            f"No rating points matched the spec in {origin}. "
            "Confirm the source columns and adjust the RatingPoint spec."
        )

    retrieved = datetime.now(UTC).strftime("%Y-%m-%d")
    header = [
        f"# SAMBA COP dataset curated from: {source_label}",
        f"# Origin: {origin}",
        f"# Retrieved (UTC): {retrieved}",
        f"# Raw SHA-256: {checksum}",
        f"# Models aggregated: {len(rows)} (per-temperature median COP)",
        "# LICENSE: LOCAL USE ONLY unless the source grants redistribution rights.",
        "#          Do NOT commit or share this file without confirming its terms.",
        "#          SAMBA does not vendor third-party HP data.",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        for line in header:
            fh.write(line + "\n")
        writer = csv.DictWriter(fh, fieldnames=["outdoor_temp_c", "cop_heating", "cop_cooling"])
        writer.writeheader()
        writer.writerows(curated)
    return out_path
