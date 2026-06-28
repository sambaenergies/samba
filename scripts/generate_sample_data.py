# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Generate SAMBA's synthetic sample load profile(s).

These are **originally generated** (algorithmic, MPL-licensed) load shapes used by
the bundled examples and golden scenarios — no third-party / external data. Run:

    uv run python scripts/generate_sample_data.py

Weather sample data is fetched separately from the public-domain NREL NSRDB API
via ``samba fetch-weather`` (not generated here).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from samba.load_profiles.templates import build_load_from_template

OUT = Path(__file__).resolve().parents[1] / "examples" / "content"

# Annual energy chosen so the mean hourly load is ~0.6 kW (a small-residential
# magnitude), keeping example/golden numbers in a sensible range.
_ANNUAL_KWH = 5256.0  # 0.6 kW * 8760 h


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    hourly = build_load_from_template("residential", annual_kwh=_ANNUAL_KWH)
    out_path = OUT / "load_residential_8760.csv"
    np.savetxt(out_path, hourly, fmt="%.6f")
    print(f"wrote {out_path}  (sum={hourly.sum():.1f} kWh, mean={hourly.mean():.3f} kW)")


if __name__ == "__main__":
    main()
