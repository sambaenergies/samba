# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Drift gate: committed ``openapi.json`` must match the live FastAPI document.

If a service route or model changes without regenerating, this fails. Fix by
running ``just openapi`` (``uv run python scripts/export_openapi.py``) and
committing the result. Runs independently of git so ``just test`` catches drift
too. (A FastAPI/Pydantic version bump can also produce a non-substantive diff
that simply needs regenerating and committing.)
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.export_openapi import build_openapi

_OPENAPI_PATH = Path(__file__).resolve().parents[2] / "openapi.json"


def test_committed_openapi_matches_app() -> None:
    assert _OPENAPI_PATH.read_text(encoding="utf-8") == build_openapi(), (
        "openapi.json is stale -- run `just openapi` and commit."
    )


def test_openapi_contract_invariants() -> None:
    """Lock the headline contract facts an external consumer relies on."""
    from samba_service._contract import API_VERSION

    doc = json.loads(build_openapi())
    assert doc["openapi"] == "3.1.0"
    assert doc["info"]["version"] == API_VERSION
    schemas = doc["components"]["schemas"]
    for required in (
        "HealthResponse",
        "ValidateRequest",
        "ValidateResponse",
        "JobSubmitRequest",
        "JobSubmitResponse",
        "JobStatusResponse",
        "ErrorResponse",
    ):
        assert required in schemas, f"openapi.json missing component schema {required}"
