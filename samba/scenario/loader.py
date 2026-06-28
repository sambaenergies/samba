# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.

"""YAML <-> Scenario serialisation utilities.

Public API
----------
load_scenario(path)          Read a YAML file and return a validated Scenario.
dump_scenario(scenario, path) Serialise a Scenario back to YAML.
ScenarioValidationError       Raised when Pydantic validation fails; carries formatted messages.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from samba.scenario.models import Scenario

#: Schema versions this build of SAMBA can load.  Bump when the schema gains
#: a breaking change; update golden YAML files in the same PR.
_KNOWN_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0", "1.1", "2.0", "3.0", "4.0"})


class ScenarioValidationError(ValueError):
    """Raised when scenario YAML does not satisfy the Pydantic schema.

    Use :meth:'format_errors' for a human-readable summary suitable for CLI output.
    """

    def __init__(self, error: ValidationError | str) -> None:
        if isinstance(error, str):
            self._raw_errors: list[Any] = []
            super().__init__(error)
        else:
            self._raw_errors = list(error.errors(include_url=False))
            super().__init__(self.format_errors())

    def format_errors(self) -> str:
        """Return one ''field.path: message'' line per validation error."""
        if not self._raw_errors:
            return str(self.args[0]) if self.args else ""
        lines: list[str] = []
        for err in self._raw_errors:
            loc = ".".join(str(p) for p in err["loc"]) if err["loc"] else "<root>"
            msg = err["msg"]
            lines.append(f"{loc}: {msg}")
        return "\n".join(lines)


def _check_schema_version(raw: dict[str, Any]) -> None:
    """Raise :class:'ScenarioValidationError' for unknown ''schema_version'' values.

    Parameters
    ----------
    raw:
        Raw (pre-validation) YAML dict from the scenario file.

    Raises
    ------
    ScenarioValidationError
        If the ''schema_version'' key is missing or not in
        :data:'_KNOWN_SCHEMA_VERSIONS'.
    """
    v = raw.get("schema_version")
    if v not in _KNOWN_SCHEMA_VERSIONS:
        raise ScenarioValidationError(
            f"Unknown schema_version {v!r}. Known versions: {sorted(_KNOWN_SCHEMA_VERSIONS)}"
        )


def load_scenario(path: str | Path) -> Scenario:
    """Read *path*, parse YAML, and return a validated :class:'Scenario'.

    Parameters
    ----------
    path:
        Path to the scenario YAML file.

    Raises
    ------
    FileNotFoundError
        When *path* does not exist.
    ValueError
        When the YAML file contains syntax errors.
    ScenarioValidationError
        When the parsed data does not satisfy the schema.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Scenario file must contain a YAML mapping, got {type(data).__name__}")

    _check_schema_version(data)

    try:
        return Scenario.model_validate(data)
    except ValidationError as exc:
        raise ScenarioValidationError(exc) from exc


def dump_scenario(scenario: Scenario, path: str | Path) -> None:
    """Serialise *scenario* to *path* as YAML.

    Only non-None values are written; fields that default to ''None'' are
    omitted so the output stays readable.  Round-tripping via
    ''load_scenario(dump_scenario(...))'' produces an equal model.

    Parameters
    ----------
    scenario:
        A validated :class:'Scenario' instance.
    path:
        Destination file path.  Parent directories must exist.
    """
    path = Path(path)
    data = scenario.model_dump(mode="json", exclude_none=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
