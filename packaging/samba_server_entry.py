# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Frozen entry point for the SAMBA backend sidecar.

This is the program PyInstaller freezes into a standalone binary that the Tauri
desktop app launches as a sidecar. It starts the FastAPI service exactly like
``samba serve`` does, but without the Typer/Rich CLI layer.

All configuration is read from ``SAMBA_*`` environment variables at import time
by :mod:`samba_service.config`, so the launcher (the Tauri shell, or a test
harness) sets those before exec'ing this binary. See that module for the full
list (``SAMBA_HOST``, ``SAMBA_PORT``, ``SAMBA_SOLVER``, ``SAMBA_DATA_DIR``,
``SAMBA_RUN_DIR``, ``SAMBA_API_KEY``, ...).
"""

from __future__ import annotations


def main() -> None:
    # Must be the first call under __main__ in a frozen binary: a no-op today
    # (the service uses a ThreadPoolExecutor and uvicorn runs single-process),
    # but it prevents a fork-bomb if a future build uses onefile or workers > 1.
    import multiprocessing

    multiprocessing.freeze_support()

    import uvicorn

    from samba_service.config import config

    uvicorn.run(
        "samba_service.app:app",
        host=config.host,
        port=config.port,
        reload=False,
        workers=1,
    )


if __name__ == "__main__":
    main()
