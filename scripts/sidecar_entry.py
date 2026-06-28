# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""PyInstaller entry point for the bundled ``samba-service`` desktop sidecar.

This is the executable the Tauri shell spawns instead of the dev-mode
``samba`` CLI on ``PATH`` (see ``ui/src-tauri/src/samba_process.rs``). It simply
re-exposes the SAMBA Typer CLI, so the frozen binary accepts the same
``samba-service serve --port <N>`` invocation. Built by ``scripts/build_sidecar.py``.
"""

from __future__ import annotations

from multiprocessing import freeze_support

from samba_cli.main import app

if __name__ == "__main__":
    # Required so PyInstaller-frozen child processes (e.g. solver workers) behave.
    freeze_support()
    app()
