# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for the ComponentExtractor Protocol and extractor registry.

Validates:
- All registered extractors satisfy the ``ComponentExtractor`` runtime Protocol.
- Individual extractors return the expected column names given minimal stub inputs.
- Thermal bus extractor is absent-safe (returns empty dict when buses are absent).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from samba.solver.extract import (
    _EXTRACTOR_REGISTRY,
    _EXTRACTORS,
    ComponentExtractionParams,
    ComponentExtractor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIMEINDEX = pd.date_range("2024-01-01", periods=8760, freq="h")
_EMPTY_FLOW = pd.DataFrame(index=_TIMEINDEX)
_EMPTY_PARAMS = ComponentExtractionParams(timesteps=8760)


def _call(
    extractor: ComponentExtractor, groups: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Invoke extractor.extract with standardised empty DataFrames."""
    return extractor.extract(
        groups=groups,
        flow_df=_EMPTY_FLOW,
        soc_df=None,
        invest_df=None,
        timeindex=_TIMEINDEX,
        params=ComponentExtractionParams(timesteps=8760),
    )


def _get_extractor(name: str) -> ComponentExtractor:
    extractor = _EXTRACTOR_REGISTRY.get(name)
    if extractor is None:
        pytest.skip(f"Extractor '{name}' not found in registry")
    return extractor


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestExtractorProtocol:
    """All registered extractors must satisfy the ComponentExtractor Protocol."""

    def test_all_extractors_nonempty(self) -> None:
        """_EXTRACTORS must contain at least one entry."""
        assert len(_EXTRACTORS) > 0

    def test_all_extractors_implement_protocol(self) -> None:
        """Every extractor in _EXTRACTORS must be an instance of ComponentExtractor."""
        for ext in _EXTRACTORS:
            assert isinstance(ext, ComponentExtractor), (
                f"{type(ext).__name__} does not satisfy ComponentExtractor Protocol"
            )

    def test_all_extractors_have_extract_method(self) -> None:
        """Every extractor must have a callable extract() method."""
        for ext in _EXTRACTORS:
            assert callable(getattr(ext, "extract", None)), (
                f"{type(ext).__name__} missing callable extract()"
            )

    def test_registry_is_list(self) -> None:
        """_EXTRACTORS must be a plain list."""
        assert isinstance(_EXTRACTORS, list)

    def test_registry_has_expected_keys(self) -> None:
        """Stable registry keys must remain available."""
        expected = {
            "electrical_core",
            "pv",
            "battery",
            "inverter",
            "wind",
            "diesel_generator",
            "grid",
            "ev",
            "thermal_bus",
            "heat_pump",
            "thermal_storage",
            "gas_boiler",
        }
        assert expected.issubset(set(_EXTRACTOR_REGISTRY))


# ---------------------------------------------------------------------------
# ElectricalCoreExtractor — basic smoke test
# ---------------------------------------------------------------------------


class TestElectricalCoreExtractor:
    def _find(self) -> ComponentExtractor:
        return _get_extractor("electrical_core")

    def test_empty_groups_returns_zero_series(self) -> None:
        ext = self._find()
        cols, caps = _call(ext, {})
        assert set(cols) == {"eload", "unmet_load", "energy_dump"}
        assert caps == {}
        for name, series in cols.items():
            assert (series == 0.0).all(), f"Expected zeros for {name}"
            assert len(series) == 8760

    def test_returns_correct_column_names(self) -> None:
        ext = self._find()
        cols, _ = _call(ext, {})
        assert "eload" in cols
        assert "unmet_load" in cols
        assert "energy_dump" in cols


# ---------------------------------------------------------------------------
# PVExtractor
# ---------------------------------------------------------------------------


class TestPVExtractor:
    def _find(self) -> ComponentExtractor:
        return _get_extractor("pv")

    def test_empty_groups_yields_zero_pv_gen(self) -> None:
        ext = self._find()
        cols, caps = _call(ext, {})
        assert "pv_gen" in cols
        assert (cols["pv_gen"] == 0.0).all()
        assert caps == {}

    def test_no_extra_columns_without_pv_node(self) -> None:
        ext = self._find()
        cols, _ = _call(ext, {})
        assert set(cols) == {"pv_gen"}


# ---------------------------------------------------------------------------
# ThermalBusExtractor
# ---------------------------------------------------------------------------


class TestThermalBusExtractor:
    def _find(self) -> ComponentExtractor:
        return _get_extractor("thermal_bus")

    def test_no_thermal_buses_returns_empty_dicts(self) -> None:
        """When heat_bus and cool_bus are absent, extractor must return ({}, {})."""
        ext = self._find()
        cols, caps = _call(ext, {})
        assert cols == {}
        assert caps == {}

    def test_only_electrical_groups_returns_empty(self) -> None:
        """Electrical-only groups (ac_bus, dc_bus) must not trigger thermal output."""
        import oemof.solph as solph

        ac_bus = solph.Bus(label="ac_bus")
        dc_bus = solph.Bus(label="dc_bus")
        ext = self._find()
        cols, caps = _call(ext, {"ac_bus": ac_bus, "dc_bus": dc_bus})
        assert cols == {}
        assert caps == {}

    def test_heat_bus_present_returns_thermal_columns(self) -> None:
        """When heat_bus is in groups, extractor must return heat_unmet_kw and heat_load_kw."""
        import oemof.solph as solph

        heat_bus = solph.Bus(label="heat_bus")
        ext = self._find()
        cols, caps = _call(ext, {"heat_bus": heat_bus})
        assert "heat_unmet_kw" in cols
        assert "heat_load_kw" in cols
        assert caps == {}
        # Values should be zeros since there are no matching flow columns
        assert (cols["heat_unmet_kw"] == 0.0).all()
        assert (cols["heat_load_kw"] == 0.0).all()

    def test_cool_bus_present_returns_cooling_columns(self) -> None:
        """When cool_bus is in groups, extractor must return cool_unmet_kw and cool_load_kw."""
        import oemof.solph as solph

        cool_bus = solph.Bus(label="cool_bus")
        ext = self._find()
        cols, caps = _call(ext, {"cool_bus": cool_bus})
        assert "cool_unmet_kw" in cols
        assert "cool_load_kw" in cols

    def test_both_thermal_buses_returns_all_four_columns(self) -> None:
        """Both heat and cool buses → four thermal columns returned."""
        import oemof.solph as solph

        heat_bus = solph.Bus(label="heat_bus")
        cool_bus = solph.Bus(label="cool_bus")
        ext = self._find()
        cols, _ = _call(ext, {"heat_bus": heat_bus, "cool_bus": cool_bus})
        assert set(cols) == {"heat_unmet_kw", "heat_load_kw", "cool_unmet_kw", "cool_load_kw"}


# ---------------------------------------------------------------------------
# EVExtractor
# ---------------------------------------------------------------------------


class TestEVExtractor:
    def _find(self) -> ComponentExtractor:
        return _get_extractor("ev")

    def test_no_ev_nodes_returns_zero_ev_columns(self) -> None:
        """Without EV nodes, all ev_* columns must be all-zero."""
        ext = self._find()
        cols, caps = _call(ext, {})
        expected_ev_cols = {"ev_charge_kw", "ev_discharge_kw", "ev_soc_kwh", "ev_travel_kwh"}
        assert expected_ev_cols.issubset(set(cols)), (
            f"Expected EV columns {expected_ev_cols}, got {set(cols)}"
        )
        for name in expected_ev_cols:
            assert (cols[name] == 0.0).all(), f"EV column '{name}' should be zero without EV nodes"
