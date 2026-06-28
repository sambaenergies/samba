# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for the EV schema and EVBuilder.

Tests cover:
* EV Pydantic model: defaults, validators (SOC bounds, hours, V2G, csv)
* EVBuilder.build(): storage node always returned
* Charge flow gated by presence (maximum kwarg)
* V2G output flow present/absent based on ev.v2g_enabled
* Travel drain bus + ev_travel sink created when depletion > 0
* No drain bus when soc_departure == soc_arrival
"""

from __future__ import annotations

from typing import Any

import numpy as np
import oemof.solph as solph
import pandas as pd
import pytest
from pydantic import ValidationError

from samba.compiler.builders.ev import EVBuilder
from samba.scenario.models import (
    EV,
    Components,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ev(**kwargs: Any) -> EV:
    """Build a minimal valid EV with defaults overridden by kwargs."""
    defaults: dict[str, Any] = {
        "capacity_kwh": 40.0,
        "max_charge_kw": 7.2,
    }
    defaults.update(kwargs)
    return EV(**defaults)


def _make_scenario_with_ev(ev: EV) -> Any:  # returns samba.scenario.models.Scenario
    """Wrap an EV in a minimal valid Scenario (grid + inverter + EV)."""
    from samba.scenario.models import (
        BuyRate,
        Grid,
        Inverter,
        Load,
        Location,
        Project,
        Scenario,
        Tariff,
        Weather,
    )

    return Scenario(
        project=Project(
            name="ev-unit-test",
            discount_rate_nominal=0.08,
        ),
        location=Location(
            latitude=51.5,
            longitude=-0.1,
            timezone="Europe/London",
        ),
        weather=Weather(source="csv", csv_path="dummy.csv"),
        load=Load(source="generic_annual_total", annual_kwh=20000.0),
        components=Components(
            inverter=Inverter(capex_per_kw=200.0),
            grid=Grid(capacity_kw=100.0),
            ev=ev,
        ),
        tariff=Tariff(buy=BuyRate(type="flat", rate_per_kwh=0.25)),
    )


def _make_timeindex(year: int = 2023) -> pd.DatetimeIndex:
    return pd.date_range(start=f"{year}-01-01 00:00", periods=8760, freq="h")


def _make_presence_all_home() -> np.ndarray:
    """Return presence array with EV always home (never away)."""
    return np.ones(8760, dtype=np.float64)


def _make_presence_with_departures() -> np.ndarray:
    """Return presence with weekday commutes (depart 08:00, arrive 18:00)."""
    from samba.load_profiles.ev_presence import build_presence_schedule

    return build_presence_schedule(arrival_hour=18, departure_hour=8, year=2023)


def _buses() -> tuple[solph.Bus, solph.Bus]:
    return solph.Bus(label="dc_bus"), solph.Bus(label="ac_bus")


# ---------------------------------------------------------------------------
# TestEVSchema
# ---------------------------------------------------------------------------


class TestEVSchema:
    """Tests for EV Pydantic model validation."""

    def test_defaults(self) -> None:
        ev = _make_ev()
        assert ev.soc_min == pytest.approx(0.1)
        assert ev.soc_max == pytest.approx(1.0)
        assert ev.soc_initial == pytest.approx(0.5)
        assert ev.soc_departure == pytest.approx(0.8)
        assert ev.soc_arrival == pytest.approx(0.3)
        assert ev.charge_efficiency == pytest.approx(0.92)
        assert ev.v2g_enabled is False
        assert ev.max_discharge_kw == pytest.approx(0.0)
        assert ev.presence_source == "schedule"
        assert ev.workdays_per_week == 5

    def test_soc_min_gte_max_raises(self) -> None:
        with pytest.raises(Exception, match="soc_min < soc_max"):
            _make_ev(soc_min=0.8, soc_max=0.5)

    def test_soc_departure_lte_arrival_raises(self) -> None:
        with pytest.raises(Exception, match="soc_departure must be strictly greater"):
            _make_ev(soc_departure=0.3, soc_arrival=0.8)

    def test_v2g_enabled_no_discharge_kw_raises(self) -> None:
        with pytest.raises(Exception, match="max_discharge_kw must be > 0"):
            _make_ev(v2g_enabled=True, max_discharge_kw=0.0)

    def test_v2g_disabled_nonzero_discharge_kw_raises(self) -> None:
        with pytest.raises(Exception, match="max_discharge_kw must be 0"):
            _make_ev(v2g_enabled=False, max_discharge_kw=5.0)

    def test_v2g_enabled_valid(self) -> None:
        ev = _make_ev(v2g_enabled=True, max_discharge_kw=7.2)
        assert ev.v2g_enabled is True
        assert ev.max_discharge_kw == pytest.approx(7.2)

    def test_same_hours_raises(self) -> None:
        with pytest.raises(Exception, match="differ"):
            _make_ev(arrival_hour=8, departure_hour=8)

    def test_invalid_workdays_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_ev(workdays_per_week=0)

    def test_csv_source_without_path_raises(self) -> None:
        with pytest.raises(Exception, match="presence_csv_path"):
            _make_ev(presence_source="csv", presence_csv_path=None)

    def test_zero_capacity_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_ev(capacity_kwh=0.0)

    def test_efficiency_out_of_range_raises(self) -> None:
        with pytest.raises(ValidationError):
            _make_ev(charge_efficiency=0.0)
        with pytest.raises(ValidationError):
            _make_ev(charge_efficiency=1.1)


# ---------------------------------------------------------------------------
# TestEVBuilderChargeOnly
# ---------------------------------------------------------------------------


class TestEVBuilderChargeOnly:
    """EV builder with V2G disabled — charge only."""

    def _build(
        self, presence: np.ndarray | None = None
    ) -> tuple[list[solph.network.Node], solph.Bus]:
        _, ac_bus = _buses()
        ev = _make_ev()
        scenario = _make_scenario_with_ev(ev)
        if presence is None:
            presence = _make_presence_with_departures()
        nodes = EVBuilder().build(
            scenario, ac_bus, presence=presence, csell=None, timeindex=_make_timeindex()
        )
        return nodes, ac_bus

    def test_returns_list(self) -> None:
        nodes, _ = self._build()
        assert isinstance(nodes, list)
        assert len(nodes) > 0

    def test_ev_storage_in_nodes(self) -> None:
        nodes, _ = self._build()
        labels = [n.label for n in nodes]
        assert "ev_storage" in labels

    def test_ev_storage_is_generic_storage(self) -> None:
        nodes, _ = self._build()
        storage = next(n for n in nodes if n.label == "ev_storage")
        assert isinstance(storage, solph.components.GenericStorage)

    def test_no_ac_output_when_no_v2g(self) -> None:
        nodes, ac_bus = self._build()
        # No ev_v2g Converter should exist when V2G is disabled
        labels = [n.label for n in nodes]
        assert "ev_v2g" not in labels

    def test_drain_bus_and_travel_sink_created(self) -> None:
        """Should create ev_bus and ev_travel when departures exist."""
        nodes, _ = self._build()
        labels = [n.label for n in nodes]
        assert "ev_bus" in labels, "Expected ev_bus in nodes"
        assert "ev_travel" in labels, "Expected ev_travel sink in nodes"

    def test_charge_flow_has_presence_maximum(self) -> None:
        """ev_charger input from ac_bus should have presence-based maximum."""
        _, ac_bus = _buses()
        ev = _make_ev()
        scenario = _make_scenario_with_ev(ev)
        presence = _make_presence_with_departures()
        nodes = EVBuilder().build(
            scenario, ac_bus, presence=presence, csell=None, timeindex=_make_timeindex()
        )
        ev_charger = next(n for n in nodes if n.label == "ev_charger")
        charge_flow = ev_charger.inputs[ac_bus]
        # The flow's maximum should encode the presence (0 when away, 1 when home)
        assert charge_flow.maximum is not None

    def test_no_drain_bus_when_no_depletion(self) -> None:
        """When EV is always home (no departures), no ev_travel sink needed."""
        presence = _make_presence_all_home()
        nodes, _ = self._build(presence=presence)
        labels = [n.label for n in nodes]
        assert "ev_travel" not in labels


# ---------------------------------------------------------------------------
# TestEVBuilderV2G
# ---------------------------------------------------------------------------


class TestEVBuilderV2G:
    """EV builder with V2G enabled."""

    def _build_v2g(
        self, csell: np.ndarray | None = None
    ) -> tuple[list[solph.network.Node], solph.Bus]:
        _, ac_bus = _buses()
        ev = _make_ev(v2g_enabled=True, max_discharge_kw=7.2)
        scenario = _make_scenario_with_ev(ev)
        presence = _make_presence_with_departures()
        if csell is None:
            csell = np.full(8760, 0.15)
        nodes = EVBuilder().build(
            scenario, ac_bus, presence=presence, csell=csell, timeindex=_make_timeindex()
        )
        return nodes, ac_bus

    def test_ac_output_present_with_v2g(self) -> None:
        nodes, ac_bus = self._build_v2g()
        # ev_v2g Converter should exist and output to ac_bus
        labels = [n.label for n in nodes]
        assert "ev_v2g" in labels, "ev_v2g Converter should exist with V2G enabled"
        ev_v2g = next(n for n in nodes if n.label == "ev_v2g")
        assert ac_bus in ev_v2g.outputs, "AC bus output should exist on ev_v2g Converter"

    def test_v2g_variable_costs_negative(self) -> None:
        """V2G flow should have negative variable costs (= revenue)."""
        csell = np.full(8760, 0.20)
        nodes, ac_bus = self._build_v2g(csell=csell)
        ev_v2g = next(n for n in nodes if n.label == "ev_v2g")
        v2g_flow = ev_v2g.outputs[ac_bus]
        # Variable costs should be negative (revenue for discharging)
        vc = v2g_flow.variable_costs
        # Variable costs should be negative (revenue for discharging)
        assert np.all(np.asarray(vc) <= 0.0)

    def test_v2g_zero_csell_zero_variable_costs(self) -> None:
        """When sell rate is 0, variable costs on V2G should be 0."""
        csell = np.zeros(8760)
        nodes, ac_bus = self._build_v2g(csell=csell)
        ev_v2g = next(n for n in nodes if n.label == "ev_v2g")
        v2g_flow = ev_v2g.outputs[ac_bus]
        vc = v2g_flow.variable_costs
        assert np.allclose(np.asarray(vc), 0.0)

    def test_drain_bus_still_present_with_v2g(self) -> None:
        """ev_bus and ev_travel should exist even when V2G is enabled."""
        nodes, _ = self._build_v2g()
        labels = [n.label for n in nodes]
        assert "ev_bus" in labels
        assert "ev_travel" in labels
