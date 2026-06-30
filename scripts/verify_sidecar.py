# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Smoke-test a frozen ``samba-server`` binary end to end.

Boots the binary, waits for ``/health``, submits a real scenario, and asserts it
solves to ``completed`` with KPIs. Run in every per-OS build-matrix cell so a
freeze that imports cleanly but cannot actually solve is caught before it ships.

Usage::

    uv run python scripts/verify_sidecar.py <path-to-samba-server-binary>

Exit code 0 on a successful solve, 1 otherwise.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIO = REPO_ROOT / "examples" / "base_scenario.yaml"
DATA_DIR = REPO_ROOT / "examples"

HEALTH_TIMEOUT_S = 90
SOLVE_TIMEOUT_S = 300


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_sidecar.py <samba-server binary>", file=sys.stderr)
        return 2
    binary = Path(sys.argv[1]).resolve()
    if not binary.is_file():
        print(f"binary not found: {binary}", file=sys.stderr)
        return 2

    port = _free_port()
    run_dir = tempfile.mkdtemp(prefix="samba-verify-")
    env = {
        **os.environ,
        "SAMBA_HOST": "127.0.0.1",
        "SAMBA_PORT": str(port),
        "SAMBA_SOLVER": "appsi_highs",
        "SAMBA_DATA_DIR": str(DATA_DIR),
        "SAMBA_RUN_DIR": run_dir,
    }
    base = f"http://127.0.0.1:{port}"

    print(f"[verify] launching {binary.name} on :{port}")
    proc = subprocess.Popen([str(binary)], env=env)
    try:
        # Wait for readiness.
        deadline = time.time() + HEALTH_TIMEOUT_S
        ready = False
        while time.time() < deadline:
            if proc.poll() is not None:
                print(f"[verify] binary exited early (code {proc.returncode})", file=sys.stderr)
                return 1
            try:
                r = httpx.get(f"{base}/health", timeout=2.0)
                if r.status_code == 200:
                    ready = True
                    health = r.json()
                    print(
                        f"[verify] health ok: solver={health.get('solver')} "
                        f"ready={health.get('solver_ready')}"
                    )
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1.0)
        if not ready:
            print("[verify] backend never became healthy", file=sys.stderr)
            return 1

        # Submit and solve a real scenario.
        scenario = yaml.safe_load(SCENARIO.read_text())
        with httpx.Client(timeout=30.0) as client:
            submit = client.post(f"{base}/api/v1/jobs", json={"scenario": scenario})
            submit.raise_for_status()
            run_id = submit.json()["run_id"]
            print(f"[verify] submitted run {run_id}; solving...")
            start = time.time()
            while True:
                status = client.get(f"{base}/api/v1/jobs/{run_id}").json()
                state = status["status"]
                if state == "completed":
                    kpis = status.get("kpis") or {}
                    print(
                        f"[verify] SOLVED in {time.time() - start:.1f}s "
                        f"({len(kpis)} KPIs, npc={kpis.get('npc')})"
                    )
                    return 0
                if state == "failed":
                    print(f"[verify] solve FAILED: {status.get('error')}", file=sys.stderr)
                    return 1
                if time.time() - start > SOLVE_TIMEOUT_S:
                    print("[verify] solve timed out", file=sys.stderr)
                    return 1
                time.sleep(2.0)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
