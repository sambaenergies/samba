# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Export the service OpenAPI document deterministically for the published contract.

FastAPI builds the OpenAPI 3.1 document from the routes and Pydantic models (the
single source of truth). This writes it to repo-root ``openapi.json`` with sorted
keys so the output is byte-stable. A drift test
(``tests/unit/test_openapi_export.py``) re-runs ``build_openapi()`` in-memory and
fails if the committed document is stale; ``just check`` enforces the same via
``git diff -- openapi.json``. The companion ``schemas/*.schema.json`` (from
``export_schemas.py``) cover the downloadable artifact shapes; together they are
the contract the UI consumes.

Run with ``just openapi`` (or ``uv run python scripts/export_openapi.py``).
Requires the service extras (``uv sync --all-extras``) so FastAPI is importable.
"""

from __future__ import annotations

import json
from pathlib import Path

from samba_service.app import app

_OPENAPI_PATH = Path(__file__).resolve().parents[1] / "openapi.json"


def build_openapi() -> str:
    """Return the OpenAPI document as deterministic, key-sorted JSON text."""
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def write_openapi(target: Path = _OPENAPI_PATH) -> Path:
    """Write the OpenAPI document to *target*; return the path written."""
    target.write_text(build_openapi(), encoding="utf-8")
    return target


if __name__ == "__main__":
    path = write_openapi()
    print(f"wrote {path.name}")
