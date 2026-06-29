# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Vendor the committed contract into ``ui/contract/`` for the UI's build.

Copies the backend-exported ``openapi.json`` and ``schemas/*.schema.json`` into
``ui/contract/`` and writes a static ``manifest.json`` (version markers only --
**no** timestamp or commit sha, so the vendored copy is byte-stable and can be
``git diff``-gated). The UI's ``gen-types.mjs`` reads from ``ui/contract/`` rather
than the repo-root ``schemas/``, so the UI build never reaches into the Python
tree -- the whole point of the virtual split.

This vendors directly from the committed exporter output, NOT from a packaged
release bundle (that channel is deferred). Run via ``just contract-sync`` (or the
chained ``just contract``, which regenerates schemas + openapi first).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from samba_service._contract import API_VERSION, CONTRACT_VERSION

_ROOT = Path(__file__).resolve().parents[1]
_SCHEMAS_DIR = _ROOT / "schemas"
_OPENAPI = _ROOT / "openapi.json"
_DEST = _ROOT / "ui" / "contract"


def sync_contract(dest: Path = _DEST) -> list[Path]:
    """Mirror the committed contract into *dest*; return the paths written."""
    dest.mkdir(parents=True, exist_ok=True)
    # Clear previously-vendored schemas so a removed backend schema is reflected
    # (a stale copy would otherwise survive and defeat the drift gate).
    for old in dest.glob("*.schema.json"):
        old.unlink()

    written: list[Path] = []
    shutil.copyfile(_OPENAPI, dest / "openapi.json")
    written.append(dest / "openapi.json")
    for src in sorted(_SCHEMAS_DIR.glob("*.schema.json")):
        shutil.copyfile(src, dest / src.name)
        written.append(dest / src.name)

    manifest = {"api_version": API_VERSION, "contract_version": CONTRACT_VERSION}
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    written.append(dest / "manifest.json")
    return written


if __name__ == "__main__":
    for p in sync_contract():
        print(f"wrote {p.relative_to(_ROOT)}")
