# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the SAMBA backend sidecar.
#
# Freezes `samba_server_entry.py` (the FastAPI service, sans Typer CLI) into a
# standalone onedir binary the Tauri desktop app launches as a sidecar.
#
# Build via `just package-server` (preferred) or:
#   uv run pyinstaller --noconfirm --clean \
#     --distpath packaging/dist --workpath packaging/build packaging/samba-server.spec
#
# The scientific/ASGI stack loads many submodules and data files by string at
# runtime (pyomo's plugin system, oemof, pvlib's data tables, uvicorn's
# protocol/loop auto-selection), which static analysis cannot see -- so we
# collect_all() those packages and pin uvicorn's auto-imported submodules.
# Verified on Linux x86_64 (Python 3.13): boots in ~1.5s and solves a real
# scenario via the in-process `appsi_highs` solver. See packaging/README.md.

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas: list = []
binaries: list = []
hiddenimports: list = []

# Packages with runtime/dynamic imports or bundled data files.
for _pkg in ("pyomo", "oemof", "pvlib", "samba", "samba_service"):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

# uvicorn selects these by string at startup; pull them in explicitly.
hiddenimports += collect_submodules("uvicorn")
hiddenimports += [
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

a = Analysis(
    ["samba_server_entry.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],  # not used by the service; trims size
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="samba-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="samba-server",
)
