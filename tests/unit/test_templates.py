# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for the v4 built-in load-profile templates."""

from __future__ import annotations

import numpy as np
import pytest

from samba.load_profiles.templates import (
    TEMPLATE_NAMES,
    build_load_from_template,
    build_template_profile,
)


class TestTemplateProfile:
    @pytest.mark.parametrize("name", TEMPLATE_NAMES)
    def test_shape_and_normalisation(self, name: str) -> None:
        prof = build_template_profile(name)
        assert prof.shape == (8760,)
        assert np.all(prof >= 0.0)
        assert prof.mean() == pytest.approx(1.0, rel=1e-9)  # normalised to mean 1.0

    def test_unknown_name_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown load template"):
            build_template_profile("spaceship")

    def test_commercial_daytime_exceeds_night(self) -> None:
        prof = build_template_profile("commercial")
        hod = np.arange(8760) % 24
        day = prof[(hod >= 9) & (hod <= 17)].mean()
        night = prof[(hod >= 0) & (hod <= 5)].mean()
        assert day > night * 1.5  # commercial is daytime-heavy

    def test_industrial_is_flatter_than_commercial(self) -> None:
        # Industrial baseload has a lower peak-to-mean ratio than commercial.
        ind = build_template_profile("industrial")
        com = build_template_profile("commercial")
        assert ind.max() / ind.mean() < com.max() / com.mean()


class TestLoadFromTemplate:
    def test_scales_to_annual_total(self) -> None:
        load = build_load_from_template("residential", annual_kwh=12000.0)
        assert load.shape == (8760,)
        assert load.sum() == pytest.approx(12000.0, rel=1e-9)

    def test_zero_annual_raises(self) -> None:
        with pytest.raises(ValueError, match="annual_kwh > 0"):
            build_load_from_template("residential", 0.0)


class TestExpandLoadTemplate:
    def test_expand_load_via_scenario_model(self) -> None:
        from samba.load_profiles.expander import expand_load
        from samba.scenario.models import Load

        load = Load(source="template", template_name="commercial", annual_kwh=50000.0)
        arr = expand_load(load, base_dir=None, peak_month="January")
        assert arr.shape == (8760,)
        assert arr.sum() == pytest.approx(50000.0, rel=1e-9)

    def test_missing_template_name_raises(self) -> None:
        from samba.load_profiles.expander import expand_load
        from samba.scenario.models import Load

        load = Load(source="template", annual_kwh=1000.0)
        with pytest.raises(ValueError, match="template_name is required"):
            expand_load(load, base_dir=None, peak_month="January")
