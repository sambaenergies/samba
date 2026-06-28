# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Export JSON Schema for every cross-boundary contract from the Pydantic models.

The Pydantic models are the single source of truth. This writes their JSON
Schemas to ``schemas/*.schema.json``; the UI generates its TypeScript types from
those files (``ui: npm run gen:types``). A drift test
(``tests/unit/test_schema_export.py``) re-runs this in-memory and fails if the
committed schemas are stale, so backend ↔ UI types cannot silently diverge.

Run with ``just schemas`` (or ``uv run python scripts/export_schemas.py``).
"""

from __future__ import annotations

import json
from pathlib import Path

from samba.run_result.contracts import (
    DispatchContract,
    EconomicsReport,
    KpiSummary,
    SizingRow,
)
from samba.scenario.models import Scenario
from samba_service.models import (
    ErrorResponse,
    HealthResponse,
    JobStatusResponse,
    JobSubmitResponse,
    ValidateResponse,
)

_SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"

# filename (under schemas/) -> Pydantic model. One schema per cross-boundary shape.
_MODELS = {
    # Scenario input
    "scenario.schema.json": Scenario,
    # Run-result artifacts (downloaded as files; not HTTP bodies)
    "kpis.schema.json": KpiSummary,
    "economics.schema.json": EconomicsReport,
    "sizing.schema.json": SizingRow,
    "dispatch.schema.json": DispatchContract,
    # Service API envelope
    "health.schema.json": HealthResponse,
    "validate.schema.json": ValidateResponse,
    "job.schema.json": JobStatusResponse,
    "job_submit.schema.json": JobSubmitResponse,
    "error.schema.json": ErrorResponse,
}


def build_schemas() -> dict[str, str]:
    """Return ``{filename: json_text}`` for every contract schema (deterministic)."""
    out: dict[str, str] = {}
    for filename, model in _MODELS.items():
        schema = model.model_json_schema()
        out[filename] = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    return out


def write_schemas(target_dir: Path = _SCHEMAS_DIR) -> list[Path]:
    """Write all schemas to *target_dir*; return the paths written."""
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, text in build_schemas().items():
        path = target_dir / filename
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    paths = write_schemas()
    for p in sorted(paths):
        print(f"wrote {p.relative_to(_SCHEMAS_DIR.parent)}")
