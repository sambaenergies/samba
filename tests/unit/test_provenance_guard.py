# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Provenance guard: keep the codebase free of upstream-derived code.

SAMBA is an independent MPL-2.0 codebase with its own models, data, and constants
(see ``docs/acknowledgements.md`` for the project that inspired it). These tests
fail if provenance markers from that upstream project reappear in production code,
scenario configuration, or golden references, so the independence cannot silently
regress. The single acknowledgement in the docs is intentionally not scanned.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The upstream project name as a standalone token (never the substring inside
# "samba"). Written with character classes so the literal token does not appear
# anywhere in the source tree — the sole textual mention lives in
# docs/acknowledgements.md — while still matching the name at runtime.
_UPSTREAM = r"(?<![a-z])s[a]m[a](?!b)"

# Markers that must never appear in production source code.
_CODE_MARKERS = [
    _UPSTREAM,
    r"bb_hp",
    r"sam_monofacial",
    r"dataextender",
    r"calc[a-z]*rate",
    r"selecthp",
    r"\bported from",  # word-bounded: catch "Ported from <upstream>", not "exported from"
]

# Markers (incl. removed upstream data files) that must never appear in shipped
# scenario config or golden references.
_DATA_MARKERS = [
    _UPSTREAM,
    r"bb_hp",
    # The vendored tree is always referenced as a path (``_reference/...``); require
    # the trailing slash so legitimate filenames like ``cop_ashp_reference.csv`` don't
    # trip the guard.
    r"_reference/",
    r"\bmeteo\b",
    r"\beload\b",
    r"\bported from",  # word-bounded: catch "Ported from <upstream>", not "exported from"
]

_PROD_CODE_DIRS = ["samba", "samba_cli", "samba_service", "scripts"]
_DATA_GLOBS = [
    ("tests/goldens", "*.yaml"),
    ("tests/goldens", "reference.json"),
    ("examples", "*.yaml"),
    ("schemas", "*.json"),
]


def _scan(path: Path, markers: list[str]) -> list[str]:
    """Return ``"<lineno>: <line>"`` strings for every marker hit in *path*."""
    hits: list[str] = []
    patterns = [re.compile(m, re.IGNORECASE) for m in markers]
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for pat in patterns:
            if pat.search(line):
                hits.append(f"{i}: {line.strip()}")
                break
    return hits


def _production_py_files() -> list[Path]:
    files: list[Path] = []
    for d in _PROD_CODE_DIRS:
        files.extend(sorted((_REPO_ROOT / d).rglob("*.py")))
    return files


def _data_files() -> list[Path]:
    files: list[Path] = []
    for sub, pattern in _DATA_GLOBS:
        root = _REPO_ROOT / sub
        if root.exists():
            files.extend(sorted(root.rglob(pattern)))
    return files


def test_no_upstream_markers_in_production_code() -> None:
    """No upstream-provenance markers in samba/ samba_cli/ samba_service/ scripts/."""
    offenders: dict[str, list[str]] = {}
    for f in _production_py_files():
        hits = _scan(f, _CODE_MARKERS)
        if hits:
            offenders[str(f.relative_to(_REPO_ROOT))] = hits
    assert not offenders, "Upstream-provenance markers found in production code:\n" + "\n".join(
        f"  {fp}\n    " + "\n    ".join(lines) for fp, lines in offenders.items()
    )


def test_no_upstream_markers_in_shipped_config() -> None:
    """No upstream-provenance markers in scenario YAML, golden references, or schemas."""
    offenders: dict[str, list[str]] = {}
    for f in _data_files():
        hits = _scan(f, _DATA_MARKERS)
        if hits:
            offenders[str(f.relative_to(_REPO_ROOT))] = hits
    assert not offenders, "Upstream-provenance markers found in shipped config:\n" + "\n".join(
        f"  {fp}\n    " + "\n    ".join(lines) for fp, lines in offenders.items()
    )


def test_reference_tree_not_tracked() -> None:
    """The vendored ``_reference/`` tree must not be tracked by git."""
    import subprocess

    out = subprocess.run(
        ["git", "ls-files", "_reference"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    tracked = [ln for ln in out.stdout.splitlines() if ln.strip()]
    assert not tracked, (
        f"{len(tracked)} file(s) under _reference/ are tracked by git; "
        "the vendored reference tree must stay untracked."
    )


@pytest.mark.parametrize("marker", [_UPSTREAM, r"bb_hp"])
def test_marker_regex_excludes_own_name(marker: str) -> None:
    """Sanity: the upstream-name marker matches that name but never our own 'SAMBA'."""
    if marker == _UPSTREAM:
        # Build the upstream name from our own ("samba" minus the 'b') so the
        # literal token never appears in source.
        upstream = "samba".replace("b", "")
        assert re.search(marker, f"{upstream} v2", re.IGNORECASE) is not None
        assert re.search(marker, "SAMBA", re.IGNORECASE) is None
        assert re.search(marker, "samba-core", re.IGNORECASE) is None
