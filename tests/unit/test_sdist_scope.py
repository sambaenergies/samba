"""Gate: the source distribution must be scoped by an explicit allowlist.

Hatchling's default sdist ships everything the **root** ``.gitignore`` does not
exclude. ``node_modules`` is ignored by the *nested* ``ui/.gitignore``, which
hatchling never reads, so a default-configured sdist built from a working tree
shipped 38 MB across 6767 entries -- 6334 of them ``node_modules`` -- while the
same command in a clean checkout produced 1.5 MB. The artifact depended on the
state of the tree it was built in rather than on anything declared.

An allowlist in ``[tool.hatch.build.targets.sdist]`` fixes that; these tests
gate it. They assert the *configuration*, not a built artifact: hatchling lives
only in the isolated build environment and is not importable here, and adding it
as a test dependency to rebuild an sdist per run costs more than it gates. The
configuration is what regressed.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _sdist_include() -> list[str]:
    with (_ROOT / "pyproject.toml").open("rb") as fh:
        config = tomllib.load(fh)
    targets = config["tool"]["hatch"]["build"]["targets"]
    assert "sdist" in targets, (
        "pyproject.toml declares no [tool.hatch.build.targets.sdist]. Without it "
        "hatchling falls back to root-.gitignore semantics and the sdist picks up "
        "whatever happens to sit in the tree, including ui/node_modules."
    )
    return targets["sdist"]["include"]


def test_sdist_is_scoped_by_an_allowlist() -> None:
    include = _sdist_include()
    assert include, "sdist `include` is empty -- that is a denylist by omission."


def test_sdist_ships_what_the_suite_reads() -> None:
    """Paths the tests resolve by absolute path, so the sdist stays test-runnable."""
    required = {
        "/samba",
        "/samba_cli",
        "/samba_service",
        "/tests",
        "/schemas",  # tests/unit/test_schema_export.py
        "/examples",  # tests/integration/test_cop_dataset_example.py
        "/openapi.json",  # tests/unit/test_openapi_export.py
        "/CHANGELOG.md",  # tests/unit/test_version_consistency.py
        "/CITATION.cff",  # tests/unit/test_version_consistency.py
    }
    missing = required - set(_sdist_include())
    assert not missing, (
        f"sdist allowlist is missing {sorted(missing)}. Tests resolve these by "
        "absolute path from the repo root, so dropping one leaves an sdist that "
        "builds but cannot run its own test suite."
    )


def test_sdist_excludes_the_frontend() -> None:
    """ui/ is the regression's source and is not needed to build, install or test."""
    assert "/ui" not in _sdist_include()
