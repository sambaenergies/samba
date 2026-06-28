"""Unit tests for samba.load_profiles — expand_load, generic load builders."""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

EXAMPLES_CONTENT = pathlib.Path(__file__).parent.parent.parent / "examples" / "content"
ELOAD_CSV = EXAMPLES_CONTENT / "load_residential_8760.csv"


# ---------------------------------------------------------------------------
# Helpers — tiny 24-row CSV for daily-tile tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def daily_csv(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a 24-row CSV (one value per hour, normalised to 1.0 total)."""
    values = np.ones(24)
    p = tmp_path / "daily.csv"
    p.write_text("\n".join(str(v) for v in values))
    return p


@pytest.fixture()
def hourly_csv(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create an 8760-row CSV (all ones)."""
    values = np.ones(8760)
    p = tmp_path / "hourly.csv"
    p.write_text("\n".join(str(v) for v in values))
    return p


# ---------------------------------------------------------------------------
# expand_load — hourly CSV
# ---------------------------------------------------------------------------


class TestExpandHourlyCsv:
    def test_shape(self) -> None:
        from samba.load_profiles import expand_load
        from samba.scenario.models import Load

        load = Load(source="hourly_csv", csv_path=str(ELOAD_CSV))
        result = expand_load(load, base_dir=EXAMPLES_CONTENT)
        assert result.shape == (8760,)

    def test_non_negative(self) -> None:
        from samba.load_profiles import expand_load
        from samba.scenario.models import Load

        load = Load(source="hourly_csv", csv_path=str(ELOAD_CSV))
        result = expand_load(load, base_dir=EXAMPLES_CONTENT)
        assert np.all(result >= 0.0)

    def test_scale_factor_doubles_values(self) -> None:
        from samba.load_profiles import expand_load
        from samba.scenario.models import Load

        load1 = Load(source="hourly_csv", csv_path=str(ELOAD_CSV), scale_factor=1.0)
        load2 = Load(source="hourly_csv", csv_path=str(ELOAD_CSV), scale_factor=2.0)
        r1 = expand_load(load1, base_dir=EXAMPLES_CONTENT)
        r2 = expand_load(load2, base_dir=EXAMPLES_CONTENT)
        np.testing.assert_array_almost_equal(r2, r1 * 2.0)


# ---------------------------------------------------------------------------
# expand_load — daily CSV
# ---------------------------------------------------------------------------


class TestExpandDailyCsv:
    def test_shape_from_eload_daily(self) -> None:
        from samba.load_profiles import expand_load
        from samba.scenario.models import Load

        load = Load(source="hourly_csv", csv_path=str(ELOAD_CSV))
        result = expand_load(load, base_dir=EXAMPLES_CONTENT)
        assert result.shape == (8760,)

    def test_shape_from_tmp_daily(self, daily_csv: pathlib.Path) -> None:
        from samba.load_profiles import expand_load
        from samba.scenario.models import Load

        load = Load(source="daily_csv", csv_path=str(daily_csv))
        result = expand_load(load, base_dir=daily_csv.parent)
        assert result.shape == (8760,)

    def test_tiling_pattern_repeats(self, daily_csv: pathlib.Path) -> None:
        """Values from a uniform daily CSV should be identical across all days."""
        from samba.load_profiles import expand_load
        from samba.scenario.models import Load

        load = Load(source="daily_csv", csv_path=str(daily_csv))
        result = expand_load(load, base_dir=daily_csv.parent)
        assert result[0] == pytest.approx(result[24])
        assert result[0] == pytest.approx(result[48])


# ---------------------------------------------------------------------------
# expand_load — wrong row count raises ValueError
# ---------------------------------------------------------------------------


class TestExpandRowCountValidation:
    def test_hourly_csv_wrong_rows_raises(self, tmp_path: pathlib.Path) -> None:
        from samba.load_profiles import expand_load
        from samba.scenario.models import Load

        bad = tmp_path / "short.csv"
        bad.write_text("\n".join(["1.0"] * 100))
        load = Load(source="hourly_csv", csv_path=str(bad))
        with pytest.raises(ValueError):
            expand_load(load, base_dir=tmp_path)

    def test_daily_csv_wrong_rows_raises(self, tmp_path: pathlib.Path) -> None:
        from samba.load_profiles import expand_load
        from samba.scenario.models import Load

        bad = tmp_path / "bad_daily.csv"
        bad.write_text("\n".join(["1.0"] * 12))  # 12 not 24
        load = Load(source="daily_csv", csv_path=str(bad))
        with pytest.raises(ValueError):
            expand_load(load, base_dir=tmp_path)


# ---------------------------------------------------------------------------
# expand_load — monthly_total source
# ---------------------------------------------------------------------------


class TestExpandMonthlyTotal:
    def test_shape(self) -> None:
        from samba.load_profiles import DAYS_IN_MONTH, expand_load
        from samba.scenario.models import Load

        monthly_kwh = [days * 24 * 1.0 for days in DAYS_IN_MONTH]  # 1 kW flat
        load = Load(source="monthly_total", monthly_peak=monthly_kwh)
        result = expand_load(load)
        assert result.shape == (8760,)

    def test_values_positive(self) -> None:
        from samba.load_profiles import DAYS_IN_MONTH, expand_load
        from samba.scenario.models import Load

        monthly_kwh = [days * 24 * 2.0 for days in DAYS_IN_MONTH]
        load = Load(source="monthly_total", monthly_peak=monthly_kwh)
        result = expand_load(load)
        assert np.all(result > 0)


# ---------------------------------------------------------------------------
# Generic load builders
# ---------------------------------------------------------------------------


class TestBuildGenericLoad:
    def test_from_monthly_shape(self) -> None:
        from samba.load_profiles import DAYS_IN_MONTH, build_generic_load_from_monthly

        monthly_kwh = [days * 24 * 1.0 for days in DAYS_IN_MONTH]
        result = build_generic_load_from_monthly(peak_month="July", monthly_totals_kwh=monthly_kwh)
        assert result.shape == (8760,)

    def test_from_monthly_non_negative(self) -> None:
        from samba.load_profiles import DAYS_IN_MONTH, build_generic_load_from_monthly

        monthly_kwh = [days * 24 * 1.0 for days in DAYS_IN_MONTH]
        result = build_generic_load_from_monthly(peak_month="July", monthly_totals_kwh=monthly_kwh)
        assert np.all(result >= 0)

    def test_from_annual_total_shape(self) -> None:
        from samba.load_profiles import build_generic_load_from_annual_total

        result = build_generic_load_from_annual_total(
            peak_month="January", annual_total_kwh=10000.0
        )
        assert result.shape == (8760,)

    def test_from_annual_total_sum(self) -> None:
        from samba.load_profiles import build_generic_load_from_annual_total

        annual = 10000.0
        result = build_generic_load_from_annual_total(peak_month="January", annual_total_kwh=annual)
        assert result.sum() == pytest.approx(annual, rel=1e-4)

    def test_normalized_shape(self) -> None:
        from samba.load_profiles import build_generic_load_normalized

        result = build_generic_load_normalized(peak_month="July")
        assert result.shape == (8760,)

    def test_normalized_non_negative(self) -> None:
        from samba.load_profiles import build_generic_load_normalized

        result = build_generic_load_normalized(peak_month="January")
        assert np.all(result >= 0)
