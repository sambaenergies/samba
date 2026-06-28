"""Unit tests for samba.scenario - schema, loader, and round-trip."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from samba.scenario import ScenarioValidationError, dump_scenario, load_scenario
from samba.scenario.models import (
    PV,
    Battery,
    BuyRate,
    Components,
    Constraints,
    Inverter,
    Load,
    Location,
    Scenario,
    SellRate,
    ServiceCharge,
    TierLevel,
    TouPeriod,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXAMPLES_DIR: Path = Path(__file__).parent.parent.parent / "examples"


def _minimal_scenario_dict() -> dict[str, Any]:
    """Return the smallest valid scenario dict."""
    return {
        "schema_version": "1.0",
        "project": {
            "name": "Test",
            "discount_rate_nominal": 0.06,
        },
        "location": {
            "latitude": 0.0,
            "longitude": 0.0,
            "timezone": "UTC",
        },
        "weather": {
            "source": "csv",
            "csv_path": "weather.csv",
        },
        "load": {
            "source": "hourly_csv",
            "csv_path": "load.csv",
        },
        "components": {
            "inverter": {
                "capex_per_kw": 200.0,
            },
            "pv": {
                "capex_per_kw": 900.0,
            },
        },
        "tariff": {
            "buy": {
                "type": "flat",
                "rate_per_kwh": 0.10,
            },
        },
    }


def _make_scenario(**overrides: Any) -> Scenario:
    d = _minimal_scenario_dict()
    d.update(overrides)
    return Scenario.model_validate(d)


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_load_base_scenario_yaml(self) -> None:
        """examples/base_scenario.yaml loads without error."""
        path: Path = EXAMPLES_DIR / "base_scenario.yaml"
        scenario: Scenario = load_scenario(path)
        assert isinstance(scenario, Scenario)

    def test_round_trip(self, tmp_path: Path) -> None:
        """dump_scenario then load_scenario produces an identical model."""
        original: Scenario = load_scenario(EXAMPLES_DIR / "base_scenario.yaml")
        dest: Path = tmp_path / "roundtrip.yaml"
        dump_scenario(original, dest)
        reloaded: Scenario = load_scenario(dest)
        assert original == reloaded

    def test_minimal_scenario_parses(self) -> None:
        """A scenario with only the strictly required fields is valid."""
        s: Scenario = Scenario.model_validate(_minimal_scenario_dict())
        assert isinstance(s, Scenario)
        assert s.objective.type == "cost"
        assert s.constraints.max_lpsp == 0.0

    def test_pv_capacity_null_is_design_variable(self) -> None:
        """PV capacity_kw=null results in None (Investment mode)."""
        d = _minimal_scenario_dict()
        d["components"]["pv"]["capacity_kw"] = None
        s: Scenario = Scenario.model_validate(d)
        assert s.components.pv is not None
        assert s.components.pv.capacity_kw is None

    def test_pv_capacity_fixed(self) -> None:
        """PV capacity_kw=50.0 stores the value correctly."""
        d = _minimal_scenario_dict()
        d["components"]["pv"]["capacity_kw"] = 50.0
        s: Scenario = Scenario.model_validate(d)
        assert s.components.pv is not None
        assert s.components.pv.capacity_kw == pytest.approx(50.0)

    def test_schema_version_default(self) -> None:
        """schema_version defaults to '1.1' when the key is omitted at model level."""
        d = {k: v for k, v in _minimal_scenario_dict().items() if k != "schema_version"}
        s: Scenario = Scenario.model_validate(d)
        assert s.schema_version == "1.1"

    def test_objective_default_cost(self) -> None:
        """objective.type defaults to 'cost'."""
        s: Scenario = Scenario.model_validate(_minimal_scenario_dict())
        assert s.objective.type == "cost"

    def test_constraints_defaults(self) -> None:
        """All Constraints fields have sensible defaults."""
        c = Constraints()
        assert c.min_renewable_fraction == 0.0
        assert c.max_annual_diesel_l is None
        assert c.max_battery_cycles_yr is None
        assert c.max_lpsp == 0.0
        assert c.force_grid_disconnect is False

    def test_all_tariff_types_representable(self) -> None:
        """All 8 BuyRate types can be constructed without error."""
        # flat
        BuyRate(type="flat", rate_per_kwh=0.10)
        # tiered
        BuyRate(type="tiered", tiers=[TierLevel(limit_kwh=300.0, rate_per_kwh=0.10)])
        # tou
        BuyRate(
            type="tou",
            tou_schedule=[TouPeriod(name="peak", hours=[8, 9, 10], rate_per_kwh=0.20)],
        )
        # ul_tou
        BuyRate(
            type="ul_tou",
            tou_schedule=[TouPeriod(name="off", hours=list(range(24)), rate_per_kwh=0.05)],
        )
        # seasonal
        from samba.scenario.models import SeasonalRate

        BuyRate(
            type="seasonal",
            seasonal_schedule=[SeasonalRate(name="summer", months=[6, 7, 8], rate_per_kwh=0.15)],
        )
        # seasonal_tiered
        from samba.scenario.models import SeasonalTiers

        BuyRate(
            type="seasonal_tiered",
            seasonal_tiers=[
                SeasonalTiers(
                    name="winter",
                    months=[12, 1, 2],
                    tiers=[TierLevel(limit_kwh=500.0, rate_per_kwh=0.09)],
                )
            ],
        )
        # monthly
        BuyRate(type="monthly", monthly_rates=[0.10] * 12)
        # monthly_tiered
        BuyRate(
            type="monthly_tiered",
            monthly_tiers=[[TierLevel(limit_kwh=300.0, rate_per_kwh=0.10)]] * 12,
        )

    def test_battery_with_all_fields(self) -> None:
        """A fully-specified Battery model validates correctly."""
        b = Battery(
            capacity_kwh=200.0,
            power_kw=100.0,
            chemistry="li_ion",
            capex_per_kwh=350.0,
            opex_per_kwh_yr=5.0,
            lifetime_years=10,
            soc_min=0.15,
            soc_max=0.95,
            soc_initial=0.50,
            charge_efficiency=0.97,
            discharge_efficiency=0.96,
            c_rate_charge=0.5,
            c_rate_discharge=0.5,
        )
        assert b.chemistry == "li_ion"

    def test_grid_with_export(self) -> None:
        """Grid + sell rate validates without error."""
        d = _minimal_scenario_dict()
        d["components"]["grid"] = {
            "capacity_kw": 50.0,
            "export_allowed": True,
            "export_capacity_kw": 10.0,
        }
        d["tariff"]["sell"] = {"type": "flat", "rate_per_kwh": 0.05}
        s: Scenario = Scenario.model_validate(d)
        assert s.components.grid is not None
        assert s.components.grid.export_allowed is True
        assert s.tariff.sell is not None


# ---------------------------------------------------------------------------
# Validation-error tests
# ---------------------------------------------------------------------------


class TestValidationErrors:
    def test_missing_inverter_raises(self) -> None:
        """Missing components.inverter raises ValidationError."""
        from pydantic import ValidationError

        d = _minimal_scenario_dict()
        del d["components"]["inverter"]
        with pytest.raises(ValidationError, match="inverter"):
            Scenario.model_validate(d)

    def test_discount_rate_out_of_range(self) -> None:
        """discount_rate_nominal > 1 raises a validation error."""
        from pydantic import ValidationError

        d = _minimal_scenario_dict()
        d["project"]["discount_rate_nominal"] = 1.5
        with pytest.raises(ValidationError, match="discount_rate_nominal"):
            Scenario.model_validate(d)

    def test_battery_soc_ordering(self) -> None:
        """soc_min >= soc_max raises a validation error."""
        with pytest.raises(Exception, match="soc"):
            Battery(capex_per_kwh=300.0, soc_min=0.9, soc_max=0.5)

    def test_weather_csv_source_without_path(self) -> None:
        """weather.source='csv' with csv_path=null raises."""
        from pydantic import ValidationError

        d = _minimal_scenario_dict()
        d["weather"] = {"source": "csv", "csv_path": None}
        with pytest.raises(ValidationError, match="csv_path"):
            Scenario.model_validate(d)

    def test_weather_nsrdb_source_accepted(self) -> None:
        """weather.source='nsrdb' is accepted (v4 API fetch); no csv_path required."""
        d = _minimal_scenario_dict()
        d["weather"] = {"source": "nsrdb"}
        scenario = Scenario.model_validate(d)
        assert scenario.weather.source == "nsrdb"

    def test_grid_export_without_sell_rate(self) -> None:
        """grid.export_allowed=True with no tariff.sell raises at Scenario level."""
        from pydantic import ValidationError

        d = _minimal_scenario_dict()
        d["components"]["grid"] = {"capacity_kw": 50.0, "export_allowed": True}
        # No tariff.sell key
        with pytest.raises(ValidationError, match="sell"):
            Scenario.model_validate(d)

    def test_extra_field_on_pv_raises(self) -> None:
        """An unknown field on components.pv raises due to extra='forbid'."""
        from pydantic import ValidationError

        d = _minimal_scenario_dict()
        d["components"]["pv"]["unknown_field"] = 42
        with pytest.raises(ValidationError, match="unknown_field|extra"):
            Scenario.model_validate(d)

    def test_load_daily_profile_wrong_length(self) -> None:
        """load.daily_profile with 23 elements raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="24"):
            Load(source="generic", daily_profile=[1.0] * 23)

    def test_load_monthly_peak_wrong_length(self) -> None:
        """load.monthly_peak with 11 elements raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="12"):
            Load(source="generic", monthly_peak=[1.0] * 11)

    def test_load_csv_source_without_csv_path(self) -> None:
        """hourly_csv source without csv_path raises."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="csv_path"):
            Load(source="hourly_csv")

    def test_no_generation_source_raises(self) -> None:
        """Components with no generation source at all raises."""
        from pydantic import ValidationError

        with pytest.raises(
            ValidationError, match="generation source|pv|wind_turbine|diesel_generator|grid"
        ):
            Components(inverter=Inverter(capex_per_kw=200.0))

    def test_pv_derating_factor_zero(self) -> None:
        """pv.derating_factor=0 raises (must be in (0, 1])."""
        with pytest.raises(Exception, match="derating_factor"):
            PV(capex_per_kw=900.0, derating_factor=0.0)

    def test_pv_negative_capacity(self) -> None:
        """pv.capacity_kw=-10 raises."""
        with pytest.raises(Exception, match="capacity_kw"):
            PV(capex_per_kw=900.0, capacity_kw=-10.0)

    def test_battery_efficiency_zero(self) -> None:
        """battery.charge_efficiency=0 raises (must be in (0, 1])."""
        with pytest.raises(Exception, match="charge_efficiency"):
            Battery(capex_per_kwh=300.0, charge_efficiency=0.0)

    def test_location_bad_timezone(self) -> None:
        """An unknown timezone string raises ValueError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="timezone|Unknown"):
            Location(latitude=0.0, longitude=0.0, timezone="Not/A/Timezone")

    def test_service_charge_flat_missing_monthly_flat(self) -> None:
        """ServiceCharge type='flat' without monthly_flat raises."""
        with pytest.raises(Exception, match="monthly_flat"):
            ServiceCharge(type="flat")

    def test_buy_rate_tiered_missing_tiers(self) -> None:
        """BuyRate type='tiered' without tiers raises."""
        with pytest.raises(Exception, match="tiers"):
            BuyRate(type="tiered")

    def test_sell_rate_tou_missing_schedule(self) -> None:
        """SellRate type='tou' without tou_schedule raises."""
        with pytest.raises(Exception, match="tou_schedule"):
            SellRate(type="tou")

    def test_project_budget_zero_raises(self) -> None:
        """project.budget=0 raises (must be > 0 when specified)."""
        from pydantic import ValidationError

        d = _minimal_scenario_dict()
        d["project"]["budget"] = 0.0
        with pytest.raises(ValidationError, match="budget"):
            Scenario.model_validate(d)

    def test_constraints_min_renewable_out_of_range(self) -> None:
        """constraints.min_renewable_fraction=1.5 raises."""
        with pytest.raises(Exception, match="min_renewable_fraction"):
            Constraints(min_renewable_fraction=1.5)

    def test_objective_type_locked_to_cost(self) -> None:
        """objective.type must be 'cost' in v1; anything else raises."""
        from pydantic import ValidationError

        d = _minimal_scenario_dict()
        d["objective"] = {"type": "lcoe"}
        with pytest.raises(ValidationError):
            Scenario.model_validate(d)


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


class TestLoader:
    def test_file_not_found(self) -> None:
        """load_scenario on a nonexistent path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_scenario("nonexistent_scenario_xyz.yaml")

    def test_malformed_yaml_raises_value_error(self, tmp_path: Path) -> None:
        """A YAML syntax error raises ValueError, not a silent failure."""
        bad: Path = tmp_path / "bad.yaml"
        bad.write_text("key: [\n  unclosed bracket\n", encoding="utf-8")
        with pytest.raises(ValueError, match="[Ii]nvalid YAML"):
            load_scenario(bad)

    def test_scenario_validation_error_format_errors(self) -> None:
        """ScenarioValidationError.format_errors() returns one line per error."""
        from pydantic import ValidationError

        # Force a multi-field error via a direct ValidationError capture
        d = _minimal_scenario_dict()
        d["project"]["discount_rate_nominal"] = -0.5  # invalid
        d["project"]["inflation_rate"] = 2.0  # invalid

        try:
            Scenario.model_validate(d)
            pytest.fail("Expected ValidationError was not raised")
        except ValidationError as exc:
            err = ScenarioValidationError(exc)
            text: str = err.format_errors()
            lines: list[str] = [ln for ln in text.splitlines() if ln.strip()]
            # At least one line should contain useful field location info
            assert any("discount_rate_nominal" in ln or "inflation_rate" in ln for ln in lines)
            assert all(":" in ln for ln in lines), "Each line should be 'field: message'"

    def test_load_scenario_from_temp_file(self, tmp_path: Path) -> None:
        """A scenario dict written to YAML can be loaded back correctly."""
        d = _minimal_scenario_dict()
        path: Path = tmp_path / "test_scenario.yaml"
        path.write_text(yaml.dump(d, default_flow_style=False), encoding="utf-8")
        s: Scenario = load_scenario(path)
        assert s.project.name == "Test"

    def test_dump_creates_file(self, tmp_path: Path) -> None:
        """dump_scenario creates the output file."""
        s: Scenario = Scenario.model_validate(_minimal_scenario_dict())
        out: Path = tmp_path / "out.yaml"
        dump_scenario(s, out)
        assert out.exists()

    def test_dump_file_is_valid_yaml(self, tmp_path: Path) -> None:
        """The file produced by dump_scenario is valid YAML."""
        s: Scenario = Scenario.model_validate(_minimal_scenario_dict())
        out: Path = tmp_path / "out.yaml"
        dump_scenario(s, out)
        data = yaml.safe_load(out.read_text())
        assert isinstance(data, dict)
        assert data["project"]["name"] == "Test"

    def test_round_trip_equality(self, tmp_path: Path) -> None:
        """dump -> load produces a model equal to the original."""
        s: Scenario = Scenario.model_validate(_minimal_scenario_dict())
        out: Path = tmp_path / "rt.yaml"
        dump_scenario(s, out)
        s2: Scenario = load_scenario(out)
        assert s == s2

    def test_scenario_validation_error_is_value_error(self, tmp_path: Path) -> None:
        """ScenarioValidationError is a subclass of ValueError."""
        invalid: Path = tmp_path / "invalid.yaml"
        invalid.write_text(
            textwrap.dedent("""\
                project:
                  name: Bad
                  discount_rate_nominal: 99.9
            """),
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            load_scenario(invalid)
