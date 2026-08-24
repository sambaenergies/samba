# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Drift gate: every hand-maintained copy of the release version must agree.

``samba/_version.py`` is the single source of truth. ``pyproject.toml`` derives
it (``dynamic = ["version"]`` + ``[tool.hatch.version]``) so it cannot drift.
The files checked here are static and cannot derive it, so they are gated
instead of hand-audited: bump ``samba/_version.py`` and these tests tell you
what else to update.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from samba._version import __version__

_ROOT = Path(__file__).resolve().parents[2]


def test_citation_version_matches_package() -> None:
    citation = yaml.safe_load((_ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert citation["version"] == __version__, (
        f"CITATION.cff version {citation['version']!r} != samba {__version__!r} -- "
        "update CITATION.cff (version and date-released) when cutting a release."
    )


def test_changelog_documents_current_version() -> None:
    changelog = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    released = re.findall(r"^## \[?(\d+\.\d+\.\d+)\]?", changelog, flags=re.MULTILINE)
    assert released, "no released version headings found in CHANGELOG.md"
    assert released[0] == __version__, (
        f"CHANGELOG.md most recent release is {released[0]!r} but samba is "
        f"{__version__!r} -- add the release section before tagging."
    )
