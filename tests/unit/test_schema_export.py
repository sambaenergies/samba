# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Drift gate: committed ``schemas/*.schema.json`` must match the Pydantic models.

If a backend model changes without regenerating the schemas, this fails. Fix by
running ``just schemas`` (``uv run python scripts/export_schemas.py``) and
committing the result — which the UI then regenerates its types from.
"""

from __future__ import annotations

from pathlib import Path

from scripts.export_schemas import build_schemas

_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"


def test_committed_schemas_match_models() -> None:
    expected = build_schemas()
    committed = {p.name for p in _SCHEMAS_DIR.glob("*.schema.json")}

    assert committed == set(expected), (
        "schemas/ is out of sync with the export set "
        f"(committed={sorted(committed)}, expected={sorted(expected)}). "
        "Run `just schemas` and commit."
    )

    stale = [
        name
        for name, text in expected.items()
        if (_SCHEMAS_DIR / name).read_text(encoding="utf-8") != text
    ]
    assert not stale, f"stale committed schemas (run `just schemas`): {stale}"
