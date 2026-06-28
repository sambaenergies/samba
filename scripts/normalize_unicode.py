#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""
Normalize / replace common Unicode offenders in Python source files.

Each character in REPLACEMENTS is substituted with its ASCII equivalent.
The script can operate in three modes:

  --write (default)  Apply replacements in-place using an atomic write.
  --dry-run          Print what would change without modifying any file.
  --check            Exit 1 if any file would be changed; exit 0 otherwise.
                     Suitable for CI gates.

Exit codes:
  0  No files needed changes (or --write succeeded).
  1  One or more files would be / were changed (--dry-run / --check).
  2  Usage / runtime error.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import tempfile
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

# Mapping of Unicode codepoints (as escape sequences) to ASCII replacements.
# Keys use \uXXXX escapes to avoid the normalizer collapsing its own source.
REPLACEMENTS: dict[str, str] = {
    # Dashes
    "\u2013": "-",  # EN DASH
    "\u2014": "--",  # EM DASH
    "\u2012": "-",  # FIGURE DASH
    "\u2010": "-",  # HYPHEN
    "\u2011": "-",  # NON-BREAKING HYPHEN
    "\ufe58": "-",  # SMALL EM DASH
    "\ufe63": "-",  # SMALL HYPHEN-MINUS
    "\uff0d": "-",  # FULLWIDTH HYPHEN-MINUS
    # Quotes -- single / apostrophe
    "\u2018": "'",  # LEFT SINGLE QUOTATION MARK
    "\u2019": "'",  # RIGHT SINGLE QUOTATION MARK / APOSTROPHE
    "\u201a": "'",  # SINGLE LOW-9 QUOTATION MARK
    "\u201b": "'",  # SINGLE HIGH-REVERSED-9 QUOTATION MARK
    "\u2039": "'",  # SINGLE LEFT-POINTING ANGLE QUOTATION MARK
    "\u203a": "'",  # SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
    "\u0060": "'",  # GRAVE ACCENT (used as open-quote in some traditions)
    "\u00b4": "'",  # ACUTE ACCENT
    "\u02bc": "'",  # MODIFIER LETTER APOSTROPHE
    "\uff07": "'",  # FULLWIDTH APOSTROPHE
    # Quotes -- double
    "\u201c": '"',  # LEFT DOUBLE QUOTATION MARK
    "\u201d": '"',  # RIGHT DOUBLE QUOTATION MARK
    "\u201e": '"',  # DOUBLE LOW-9 QUOTATION MARK
    "\u201f": '"',  # DOUBLE HIGH-REVERSED-9 QUOTATION MARK
    "\u00ab": '"',  # LEFT-POINTING DOUBLE ANGLE QUOTATION MARK
    "\u00bb": '"',  # RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK
    "\uff02": '"',  # FULLWIDTH QUOTATION MARK
    # Spaces
    "\u00a0": " ",  # NO-BREAK SPACE
    "\u202f": " ",  # NARROW NO-BREAK SPACE
    "\u2009": " ",  # THIN SPACE
    "\u200a": " ",  # HAIR SPACE
    "\u3000": " ",  # IDEOGRAPHIC SPACE
    # Ellipsis
    "\u2026": "...",  # HORIZONTAL ELLIPSIS
    # Multiplication / comparison
    "\u00d7": "x",  # MULTIPLICATION SIGN
    "\u2212": "-",  # MINUS SIGN
    # Other punctuation
    "\u2022": "*",  # BULLET
    "\u2023": "*",  # TRIANGULAR BULLET
    "\u00b7": "*",  # MIDDLE DOT
    "\u2044": "/",  # FRACTION SLASH
    "\ufe64": "<",  # SMALL LESS-THAN SIGN
    "\ufe65": ">",  # SMALL GREATER-THAN SIGN
    # ---------------------------------------------------------------------------
    # Arrows (used heavily in docstring ASCII topology diagrams)
    # ---------------------------------------------------------------------------
    "\u2192": "->",  # RIGHTWARDS ARROW (->)
    "\u2190": "<-",  # LEFTWARDS ARROW (<-)
    "\u2193": "|",  # DOWNWARDS ARROW (|)  -- vertical flow in diagrams
    "\u2194": "<->",  # LEFT RIGHT ARROW (<->)
    "\u2198": "->",  # SOUTH EAST ARROW (->)
    # ---------------------------------------------------------------------------
    # Box-drawing characters (used in module-level topology docstrings)
    # ---------------------------------------------------------------------------
    "\u2500": "-",  # BOX DRAWINGS LIGHT HORIZONTAL (-)
    "\u2502": "|",  # BOX DRAWINGS LIGHT VERTICAL (|)
    "\u250c": "+",  # BOX DRAWINGS LIGHT DOWN AND RIGHT (+)
    "\u2510": "+",  # BOX DRAWINGS LIGHT DOWN AND LEFT (+)
    "\u2514": "+",  # BOX DRAWINGS LIGHT UP AND RIGHT (+)
    "\u2518": "+",  # BOX DRAWINGS LIGHT UP AND LEFT (+)
    "\u251c": "+",  # BOX DRAWINGS LIGHT VERTICAL AND RIGHT (+)
    "\u2524": "+",  # BOX DRAWINGS LIGHT VERTICAL AND LEFT (+)
    "\u252c": "+",  # BOX DRAWINGS LIGHT DOWN AND HORIZONTAL (+)
    "\u2534": "+",  # BOX DRAWINGS LIGHT UP AND HORIZONTAL (+)
    "\u253c": "+",  # BOX DRAWINGS LIGHT VERTICAL AND HORIZONTAL (+)
    # ---------------------------------------------------------------------------
    # Math / comparison operators
    # ---------------------------------------------------------------------------
    "\u2265": ">=",  # GREATER-THAN OR EQUAL TO (>=)
    "\u2264": "<=",  # LESS-THAN OR EQUAL TO (<=)
    "\u2248": "~=",  # ALMOST EQUAL TO (~=)
    # ---------------------------------------------------------------------------
    # Superscripts and subscripts (appear in unit strings: h-1, kWh/m2, CO2)
    # ---------------------------------------------------------------------------
    "\u207b": "-",  # SUPERSCRIPT MINUS (-)  -> h-1
    "\u00b9": "1",  # SUPERSCRIPT ONE (1)    -> h-1
    "\u00b2": "2",  # SUPERSCRIPT TWO (2)    -> m2
    "\u00b3": "3",  # SUPERSCRIPT THREE (3)  -> m3
    "\u2070": "0",  # SUPERSCRIPT ZERO (0)
    "\u00b0": "deg",  # DEGREE SIGN (deg)        -> 20deg
    "\u2082": "2",  # SUBSCRIPT TWO (2)      -> CO2
    "\u2083": "3",  # SUBSCRIPT THREE (3)
    "\u2081": "1",  # SUBSCRIPT ONE (1)
    # ---------------------------------------------------------------------------
    # Greek letters (appear in physics/engineering docstrings)
    # ---------------------------------------------------------------------------
    "\u03b1": "alpha",  # GREEK SMALL LETTER ALPHA (alpha)
    "\u03b2": "beta",  # GREEK SMALL LETTER BETA (beta)
    "\u03b3": "gamma",  # GREEK SMALL LETTER GAMMA (gamma)
    "\u03b7": "eta",  # GREEK SMALL LETTER ETA (eta)
    "\u03bb": "lambda",  # GREEK SMALL LETTER LAMBDA (lambda)
    "\u03bc": "mu",  # GREEK SMALL LETTER MU (mu)
    "\u03c0": "pi",  # GREEK SMALL LETTER PI (pi)
    "\u03c3": "sigma",  # GREEK SMALL LETTER SIGMA (sigma)
    "\u03c9": "omega",  # GREEK SMALL LETTER OMEGA (omega)
    "\u0394": "Delta",  # GREEK CAPITAL LETTER DELTA (Delta)
    "\u03a9": "Omega",  # GREEK CAPITAL LETTER OMEGA (Omega)
    # ---------------------------------------------------------------------------
    # Currency
    # ---------------------------------------------------------------------------
    "\u20ac": "EUR",  # EURO SIGN (EUR)
    "\u00a3": "GBP",  # POUND SIGN (GBP)
    "\u00a5": "JPY",  # YEN SIGN (JPY)
    # ---------------------------------------------------------------------------
    # Section / reference markers
    # ---------------------------------------------------------------------------
    "\u00a7": "Sec.",  # SECTION SIGN (Sec.)  e.g. "Sec.Bus Architecture" -> "Sec.Bus Architecture"
    "\u00b6": "P.",  # PILCROW SIGN (P.)
    # ---------------------------------------------------------------------------
    # Misc symbols appearing in comments / CLI output
    # ---------------------------------------------------------------------------
    "\u2713": "(ok)",  # CHECK MARK ((ok))
    "\u2717": "(x)",  # BALLOT X ((x))
    "\u2714": "(ok)",  # HEAVY CHECK MARK ((ok))
    "\u2718": "(x)",  # HEAVY BALLOT X ((x))
}


# ---------------------------------------------------------------------------
# File collection (mirrors detect_unicode.py)
# ---------------------------------------------------------------------------


def _is_excluded(path: pathlib.Path, exclude_dirs: frozenset[str]) -> bool:
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
# Normalization
# ---------------------------------------------------------------------------


def _apply(text: str) -> tuple[str, dict[str, int]]:
    """Apply REPLACEMENTS to *text*.  Returns (new_text, counts) where counts
    maps each replacement character to the number of substitutions made."""
    counts: dict[str, int] = {}
    for src, dst in REPLACEMENTS.items():
        if src in text:
            n = text.count(src)
            text = text.replace(src, dst)
            counts[src] = n
    return text, counts


def _atomic_write(path: pathlib.Path, content: str) -> None:
    """Write *content* to *path* atomically (via a temp file in the same dir)."""
    tmp: pathlib.Path | None = None
    try:
        fd, tmp_str = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        tmp = pathlib.Path(tmp_str)
        with open(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        tmp.replace(path)
    except Exception:
        if tmp is not None and tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _fmt_counts(counts: dict[str, int]) -> str:
    parts = [
        f"U+{ord(ch):04X}({n}x)" for ch, n in sorted(counts.items(), key=lambda kv: ord(kv[0]))
    ]
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="normalize_unicode.py",
        description="Replace common Unicode offenders with ASCII equivalents.",
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
        "--git-tracked-only",
        action="store_true",
        help="Only scan git-tracked files; falls back to directory walk if git is unavailable.",
    )

    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--write",
        dest="mode",
        action="store_const",
        const="write",
        default="write",
        help="Apply replacements in-place (default).",
    )
    mode.add_argument(
        "--dry-run",
        dest="mode",
        action="store_const",
        const="dry-run",
        help="Print what would change without writing.",
    )
    mode.add_argument(
        "--check",
        dest="mode",
        action="store_const",
        const="check",
        help="Exit 1 if any file would be changed (CI gate).",
    )
    return p.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    try:
        args = _parse_args(argv)
        root = pathlib.Path(args.root).resolve()
        exclude_dirs: frozenset[str] = DEFAULT_EXCLUDE_DIRS | frozenset(args.exclude_dir)
        targets = [root / p for p in args.paths]

        files = _collect_files(
            targets,
            exclude_dirs=exclude_dirs,
            root=root,
            git_only=args.git_tracked_only,
        )

        # list of (path, counts, delta) for changed files
        changed: list[tuple[pathlib.Path, dict[str, int], int]] = []

        for path in files:
            try:
                original = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                print(
                    f"warning: {path.relative_to(root)}: not valid UTF-8, skipping",
                    file=sys.stderr,
                )
                continue

            normalized, counts = _apply(original)
            if not counts:
                continue

            delta = len(original) - len(normalized)
            changed.append((path, counts, delta))

            if args.mode == "write":
                _atomic_write(path, normalized)

        if not changed:
            print(f"OK: no replacements needed in {len(files)} file(s).")
            return 0

        for path, counts, delta in changed:
            rel = path.relative_to(root)
            verb = "would change" if args.mode in ("dry-run", "check") else "changed"
            print(f"{rel}: {verb} -- {_fmt_counts(counts)} (net -{delta} chars)")

        if args.mode == "write":
            print(f"\n{len(changed)} file(s) updated.")
            return 0

        if args.mode == "check":
            print(f"\n{len(changed)} file(s) would be changed. Run --write to fix.")
            return 1

        # dry-run
        print(f"\n{len(changed)} file(s) would be changed (dry run, no files written).")
        return 1

    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
