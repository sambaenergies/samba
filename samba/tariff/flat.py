# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Flat electricity rate: constant $/kWh for all 8 760 hours."""

from __future__ import annotations

import numpy as np


def calc_flat_rate(rate: float) -> np.ndarray:
    """Return an 8 760-element array filled with *rate* [$/kWh].

    Parameters
    ----------
    rate:
        Constant electricity price [$/kWh].
    """
    return np.full(8760, rate, dtype=np.float64)
