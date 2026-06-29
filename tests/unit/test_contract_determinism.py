# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""The contract exporters must be byte-deterministic.

Both ``schemas/*.schema.json`` and the committed ``openapi.json`` are consumed by
the UI (vendored into ``ui/contract/``) and a compatibility gate, so their export
has to be reproducible. This locks in run-to-run (within-process) determinism;
*cross-version* stability is covered separately by the Python test matrix running
the drift gates (``test_schema_export`` / ``test_openapi_export``) on every
supported interpreter -- which is how the 3.13 ``http.HTTPStatus`` 422 phrase
change was caught and pinned.

Neither exporter embeds a timestamp or commit sha today; if one is ever added it
must be zeroed (e.g. ``SOURCE_DATE_EPOCH``) before comparison. This test also
guards against that regressing.
"""

from __future__ import annotations

from scripts.export_openapi import build_openapi
from scripts.export_schemas import build_schemas


def test_build_schemas_is_byte_deterministic() -> None:
    assert build_schemas() == build_schemas()


def test_build_openapi_is_byte_deterministic() -> None:
    from samba_service.app import app

    first = build_openapi()
    # Bust FastAPI's per-process cache so the second call genuinely regenerates
    # the document rather than returning the memoised one.
    app.openapi_schema = None
    second = build_openapi()
    assert first == second
