#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""
Detect non-ASCII and problematic Unicode characters in Python source files.

Policy: source files should be ASCII-only. Any non-ASCII character (except
those explicitly allowlisted) is reported. Zero-width characters, bidi
controls, and surrogate code points are always reported regardless of the
allowlist.

Exit codes:
  0  No issues found.
  1  One or more issues found.
  2  Usage / runtime error.
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import re
import subprocess
import sys
import unicodedata
from collections.abc import Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Paths scanned when no positional arguments are given.
DEFAULT_SCAN_PATHS: list[str] = ["samba", "samba_cli", "samba_service", "scripts"]

# Directory names that are never descended into.
DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
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
        "_reference",
    }
)

# Characters always reported regardless of the allowlist.
_ALWAYS_BAD: frozenset[int] = frozenset(
    {
        0x00A0,  # NO-BREAK SPACE
        0x200B,  # ZERO WIDTH SPACE
        0x200C,  # ZERO WIDTH NON-JOINER
        0x200D,  # ZERO WIDTH JOINER
        0x2060,  # WORD JOINER
        0xFEFF,  # BOM / ZERO WIDTH NO-BREAK SPACE
        # Bidi controls
        0x061C,  # ARABIC LETTER MARK
        0x200E,
        0x200F,  # LRM, RLM
        0x202A,
        0x202B,
        0x202C,  # LRE, RLE, PDF
        0x202D,
        0x202E,  # LRO, RLO
        0x2066,
        0x2067,
        0x2068,
        0x2069,  # LRI, RLI, FSI, PDI
    }
)

_ALLOWLIST_LINE = re.compile(r"^\s*(?:#.*)?$|^\s*U\+([0-9A-Fa-f]{4,6})\s*(?:#.*)?$")


@dataclasses.dataclass(frozen=True)
class Finding:
    rel_path: str  # path relative to repo root
    line: int  # 1-based line number
    col: int  # 1-based column number
    codepoint: int  # Unicode code point value
    name: str  # Unicode character name
    category: str  # Unicode general category (e.g. "Sm", "Pd")
    line_text: str  # source line without trailing newline

    def format(self) -> str:
        cp = f"U+{self.codepoint:04X}"
        caret = " " * (self.col - 1) + "^"
        return (
            f"{self.rel_path}:{self.line}:{self.col}: {cp} {self.name} [{self.category}]\n"
            f"    {self.line_text}\n"
            f"    {caret}"
        )


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------


def _is_excluded(path: pathlib.Path, exclude_dirs: frozenset[str]) -> bool:
    """Return True if any component of *path* is in *exclude_dirs*."""
    return any(part in exclude_dirs for part in path.parts)


def _git_py_files(root: pathlib.Path, targets: list[pathlib.Path]) -> list[pathlib.Path] | None:
    """Return git-tracked .py files under *targets*, or None if git is unavailable."""
    try:
        rel = [str(t.relative_to(root)) for t in targets]
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--"] + rel,
            capture_output=True,
            check=True,
        )
    except Exception:
        return None
    parts = result.stdout.split(b"\x00")
    return [root / p.decode() for p in parts if p and (root / p.decode()).suffix == ".py"]


def _collect_files(
    targets: list[pathlib.Path],
    *,
    exclude_dirs: frozenset[str],
    root: pathlib.Path,
    git_only: bool,
) -> list[pathlib.Path]:
    """Return a sorted, deduplicated list of .py files to scan."""
    if git_only:
        tracked = _git_py_files(root, targets)
        if tracked is not None:
            return sorted(p for p in tracked if not _is_excluded(p, exclude_dirs))
        # git unavailable -- fall through to directory walk

    seen: set[pathlib.Path] = set()
    files: list[pathlib.Path] = []
    for target in targets:
        candidates: list[pathlib.Path] = (
            [target] if target.is_file() else list(target.rglob("*.py"))
        )
        for p in candidates:
            rp = p.resolve()
            if rp in seen or not p.is_file():
                continue
            seen.add(rp)
            if not _is_excluded(p, exclude_dirs):
                files.append(p)
    return sorted(files)


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def _load_allowlist(path: pathlib.Path) -> frozenset[int]:
    allowed: set[int] = set()
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = _ALLOWLIST_LINE.match(line)
        if not m:
            raise ValueError(f"Invalid allowlist line {i}: {line!r}  (expected 'U+XXXX')")
        if m.group(1):
            allowed.add(int(m.group(1), 16))
    return frozenset(allowed)


def _scan_text(
    text: str,
    *,
    rel_path: str,
    allowlist: frozenset[int],
    max_findings: int,
) -> list[Finding]:
    findings: list[Finding] = []
    for li, raw_line in enumerate(text.splitlines(), 1):
        for ci, ch in enumerate(raw_line, 1):
            cp = ord(ch)
            # Printable ASCII (0x20..0x7E) and tab: always OK.
            if 0x20 <= cp <= 0x7E or ch == "\t":
                continue
            always_bad = cp in _ALWAYS_BAD or 0xD800 <= cp <= 0xDFFF
            if not always_bad and cp in allowlist:
                continue
            findings.append(
                Finding(
                    rel_path=rel_path,
                    line=li,
                    col=ci,
                    codepoint=cp,
                    name=unicodedata.name(ch, "UNKNOWN"),
                    category=unicodedata.category(ch),
                    line_text=raw_line,
                )
            )
            if len(findings) >= max_findings:
                return findings
    return findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="detect_unicode.py",
        description="Report non-ASCII and control characters in Python source files.",
    )
    p.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repository root (default: parent of scripts/).",
    )
    p.add_argument(
        "paths",
        nargs="*",
        default=DEFAULT_SCAN_PATHS,
        help=(f"Paths to scan, relative to --root (default: {' '.join(DEFAULT_SCAN_PATHS)})."),
    )
    p.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        metavar="DIR",
        help="Additional directory name to exclude (repeatable).",
    )
    p.add_argument(
        "--allowlist-file",
        metavar="FILE",
        help=(
            "File of codepoints to ignore, one per line as 'U+XXXX' "
            "(blank lines and # comments accepted)."
        ),
    )
    p.add_argument(
        "--git-tracked-only",
        action="store_true",
        help="Only scan git-tracked files; falls back to directory walk if git is unavailable.",
    )
    p.add_argument(
        "--max-findings",
        type=int,
        default=200,
        help="Stop after this many findings (default: 200).",
    )
    return p.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    try:
        args = _parse_args(argv)
        root = pathlib.Path(args.root).resolve()
        exclude_dirs: frozenset[str] = DEFAULT_EXCLUDE_DIRS | frozenset(args.exclude_dir)
        targets = [root / p for p in args.paths]

        allowlist: frozenset[int] = frozenset()
        if args.allowlist_file:
            af = pathlib.Path(args.allowlist_file)
            if not af.is_absolute():
                af = (root / af).resolve()
            allowlist = _load_allowlist(af)

        files = _collect_files(
            targets,
            exclude_dirs=exclude_dirs,
            root=root,
            git_only=args.git_tracked_only,
        )

        all_findings: list[Finding] = []
        for path in files:
            budget = max(1, args.max_findings - len(all_findings))
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                print(
                    f"warning: {path.relative_to(root)}: not valid UTF-8, skipping",
                    file=sys.stderr,
                )
                continue
            all_findings.extend(
                _scan_text(
                    text,
                    rel_path=str(path.relative_to(root)),
                    allowlist=allowlist,
                    max_findings=budget,
                )
            )
            if len(all_findings) >= args.max_findings:
                break

        if all_findings:
            print(f"Non-ASCII / control characters found ({len(all_findings)} finding(s)):\n")
            for f in all_findings:
                print(f.format())
                print()
            return 1

        print(f"OK: no non-ASCII characters found in {len(files)} file(s).")
        return 0

    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
