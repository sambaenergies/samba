# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Tests that unknown schema_version values are rejected early by load_scenario."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


class TestSchemaVersionValidation:
    """_check_schema_version blocks unrecognised schema versions."""

    def _dump_yaml(self, tmp_path: Path, data: dict) -> Path:  # type: ignore[type-arg]
        p = tmp_path / "scenario.yaml"
        p.write_text(yaml.dump(data), encoding="utf-8")
        return p

    def _minimal_raw(self) -> dict:  # type: ignore[type-arg]
        """Return the minimal valid raw dict (schema_version will be overridden)."""
        return {
            "schema_version": "1.0",
            "project": {
                "name": "sv-test",
                "lifetime_years": 20,
                "discount_rate_nominal": 0.05,
                "inflation_rate": 0.02,
            },
            "location": {
                "latitude": 37.77,
                "longitude": -122.42,
                "timezone": "America/Los_Angeles",
            },
            "weather": {"source": "csv", "csv_path": "dummy.csv"},
            "load": {"source": "generic_annual_total", "annual_kwh": 8760.0},
            "tariff": {"buy": {"type": "flat", "rate_per_kwh": 0.15}},
            "components": {
                "inverter": {"capex_per_kw": 200.0, "capacity_kw": 5.0},
                "grid": {"capacity_kw": 20.0},
            },
        }

    # ------------------------------------------------------------------
    # Known versions — must NOT raise
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("version", ["1.0", "1.1", "2.0"])
    def test_known_version_accepted(self, version: str, tmp_path: Path) -> None:
        """Known schema versions load without error."""
        from samba.scenario import ScenarioValidationError, load_scenario

        raw = self._minimal_raw()
        raw["schema_version"] = version
        p = self._dump_yaml(tmp_path, raw)

        # May raise if Pydantic rejects field values, but NOT ScenarioValidationError
        # about the version.  For "1.0" / "1.1" we expect a clean load.
        try:
            load_scenario(p)
        except ScenarioValidationError as exc:
            # Acceptable only if the error is NOT about schema_version
            assert "schema_version" not in str(exc).lower() or "unknown" not in str(exc).lower(), (
                f"load_scenario raised on schema_version='{version}': {exc}"
            )

    # ------------------------------------------------------------------
    # Unknown versions — must raise ScenarioValidationError
    # ------------------------------------------------------------------

    def test_unknown_version_raises(self, tmp_path: Path) -> None:
        """schema_version '9.9' must raise ScenarioValidationError immediately."""
        from samba.scenario import ScenarioValidationError, load_scenario

        raw = self._minimal_raw()
        raw["schema_version"] = "9.9"
        p = self._dump_yaml(tmp_path, raw)

        with pytest.raises(ScenarioValidationError, match="9.9"):
            load_scenario(p)

    def test_missing_version_raises(self, tmp_path: Path) -> None:
        """Missing schema_version raises ScenarioValidationError."""
        from samba.scenario import ScenarioValidationError, load_scenario

        raw = self._minimal_raw()
        del raw["schema_version"]
        p = self._dump_yaml(tmp_path, raw)

        with pytest.raises(ScenarioValidationError, match="None"):
            load_scenario(p)

    def test_error_message_contains_known_versions(self, tmp_path: Path) -> None:
        """Error message lists the known schema versions."""
        from samba.scenario import ScenarioValidationError, load_scenario

        raw = self._minimal_raw()
        raw["schema_version"] = "0.0"
        p = self._dump_yaml(tmp_path, raw)

        with pytest.raises(ScenarioValidationError) as exc_info:
            load_scenario(p)

        msg = str(exc_info.value)
        assert "1.0" in msg
        assert "1.1" in msg
        assert "2.0" in msg

    # ------------------------------------------------------------------
    # Direct function test (no file I/O)
    # ------------------------------------------------------------------

    def test_check_schema_version_function_unknown(self) -> None:
        """_check_schema_version raises for unknown version dict."""
        from samba.scenario.loader import ScenarioValidationError, _check_schema_version

        with pytest.raises(ScenarioValidationError, match="Unknown"):
            _check_schema_version({"schema_version": "99.0"})

    def test_check_schema_version_function_known(self) -> None:
        """_check_schema_version does not raise for known versions."""
        from samba.scenario.loader import _check_schema_version

        for v in ["1.0", "1.1", "2.0"]:
            _check_schema_version({"schema_version": v})  # must not raise


# ---------------------------------------------------------------------------
# Golden scenario.yaml files must all use known schema versions
# ---------------------------------------------------------------------------

_GOLDENS_DIR = Path(__file__).parent.parent / "goldens"
_GOLDEN_YAML_FILES = sorted(_GOLDENS_DIR.glob("*/scenario.yaml"))


@pytest.mark.parametrize(
    "scenario_path",
    _GOLDEN_YAML_FILES,
    ids=[p.parent.name for p in _GOLDEN_YAML_FILES],
)
def test_golden_schema_versions_known(scenario_path: Path) -> None:
    """All golden scenario.yaml files use a version in _KNOWN_SCHEMA_VERSIONS."""
    from samba.scenario.loader import _KNOWN_SCHEMA_VERSIONS

    data = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{scenario_path} is not a YAML mapping"
    v = data.get("schema_version")
    assert v in _KNOWN_SCHEMA_VERSIONS, (
        f"{scenario_path.parent.name}/scenario.yaml has schema_version={v!r}, "
        f"which is not in {sorted(_KNOWN_SCHEMA_VERSIONS)}"
    )
