# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Build the self-contained ``samba-service`` sidecar binary with PyInstaller.

Produces a one-file executable that bundles the Python runtime, the SAMBA
packages, and the full scientific stack (oemof-solph, Pyomo, HiGHS via highspy,
pvlib) so the desktop app needs no Python installed. Output is named for the
Rust host target triple, which is what Tauri's ``externalBin`` mechanism expects
(``binaries/samba-service-<triple>``).

The HiGHS solver is a pip wheel (``highspy``) — there is **no** separate CBC/GLPK
binary to download or bundle.

Usage::

    uv run python scripts/build_sidecar.py            # build for the host triple
    uv run python scripts/build_sidecar.py --triple x86_64-unknown-linux-gnu

Requires ``pyinstaller`` (install: ``uv pip install pyinstaller``). Cross-OS
builds are not possible — run on each target OS (in CI) for that platform.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ENTRY = _ROOT / "scripts" / "sidecar_entry.py"
_OUT_DIR = _ROOT / "ui" / "src-tauri" / "binaries"

# Packages PyInstaller's static analysis misses (dynamic imports / data files).
_COLLECT_ALL = ["samba", "samba_cli", "samba_service", "oemof", "pyomo", "highspy", "pvlib"]
_HIDDEN = [
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.loops.auto",
]


def _host_triple() -> str:
    out = subprocess.run(["rustc", "-Vv"], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("could not determine host target triple from `rustc -Vv`")


def build(triple: str) -> Path:
    work = _ROOT / "build" / "sidecar"
    dist = _ROOT / "dist" / "sidecar"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--noconfirm",
        "--clean",
        "--name",
        "samba-service",
        "--console",
        "--workpath",
        str(work),
        "--distpath",
        str(dist),
        "--specpath",
        str(work),
    ]
    for pkg in _COLLECT_ALL:
        cmd += ["--collect-all", pkg]
    for mod in _HIDDEN:
        cmd += ["--hidden-import", mod]
    cmd.append(str(_ENTRY))

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=_ROOT)

    built = dist / ("samba-service.exe" if sys.platform == "win32" else "samba-service")
    suffix = ".exe" if sys.platform == "win32" else ""
    target = _OUT_DIR / f"samba-service-{triple}{suffix}"
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, target)
    target.chmod(0o755)
    size_mb = target.stat().st_size // (1024 * 1024)
    print(f"\nSidecar ready: {target.relative_to(_ROOT)}  ({size_mb} MB)")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--triple", default=None, help="Rust target triple (default: host)")
    args = parser.parse_args()
    build(args.triple or _host_triple())
