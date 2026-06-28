#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""
Check that every Python file in the target paths carries the MPL-2.0 header.

Expected first line (exactly):
    # This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.

Exit codes:
  0  All files have the header (or no files were found).
  1  One or more files are missing the header.
  2  Usage / runtime error.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Iterable

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

MPL_FIRST_LINE = (
    "# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0."
)

DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".tox",
    ".nox",
    "build",
    "dist",
    "node_modules",
    ".idea",
    ".vscode",
    "_reference",  # legacy reference code; not subject to MPL header requirement
}

# Paths scanned by default (relative to repo root).
DEFAULT_SCAN_PATHS = [
    "samba",
    "samba_cli",
    "samba_service",
    "scripts",
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="check_mpl_headers.py",
        description="Verify MPL-2.0 header presence in Python source files.",
    )
    p.add_argument(
        "paths",
        nargs="*",
        default=DEFAULT_SCAN_PATHS,
        help=(
            "Paths (files or directories) to check, relative to --root. "
            f"Default: {' '.join(DEFAULT_SCAN_PATHS)}"
        ),
    )
    p.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repo root (default: scripts/..).",
    )
    p.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help=(
            "Additional directory name to exclude (can repeat). "
            "Default set already includes .git, .venv, _reference, etc."
        ),
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-file output; only print the final summary.",
    )
    return p.parse_args(argv)


def iter_python_files(
    targets: list[pathlib.Path],
    exclude_dirs: set[str],
) -> Iterable[pathlib.Path]:
    for target in targets:
        if target.is_file():
            if target.suffix == ".py":
                yield target
        elif target.is_dir():
            for py in target.rglob("*.py"):
                if any(part in exclude_dirs for part in py.relative_to(target).parts):
                    continue
                yield py


def has_mpl_header(path: pathlib.Path) -> bool:
    """Return True if *path* contains the MPL first-line within its first 6 lines.

    Tolerates an optional shebang on line 1 and any ordering of comment lines
    before the module docstring.
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            for _ in range(6):
                line = fh.readline()
                if not line:
                    break
                stripped = line.strip()
                if stripped.startswith("#!"):
                    continue  # skip shebang
                if stripped == MPL_FIRST_LINE:
                    return True
                # Stop as soon as we hit non-comment, non-blank content.
                if stripped and not stripped.startswith("#"):
                    break
    except (OSError, UnicodeDecodeError):
        pass
    return False


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        root = pathlib.Path(args.root).resolve()
        exclude_dirs = DEFAULT_EXCLUDE_DIRS | set(args.exclude_dir or [])

        targets = [root / p for p in args.paths]
        missing: list[pathlib.Path] = []

        files = sorted(iter_python_files(targets, exclude_dirs))
        for path in files:
            if not has_mpl_header(path):
                missing.append(path)
                if not args.quiet:
                    print(f"MISSING MPL header: {path.relative_to(root)}")

        total = len(files)
        n_missing = len(missing)

        if n_missing:
            print(f"\n{n_missing}/{total} file(s) missing MPL-2.0 header.")
            return 1

        print(f"All {total} file(s) carry the MPL-2.0 header.")
        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
