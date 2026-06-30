# Packaging — frozen backend sidecar

Freezes the SAMBA FastAPI backend (`samba serve`, minus the Typer CLI) into a
standalone binary that the Tauri desktop app launches as a sidecar. This is the
foundation of the cross-platform desktop app epic.

## Files

- **`samba_server_entry.py`** — the frozen entry point. Starts uvicorn on
  `samba_service.app:app`. All config comes from `SAMBA_*` env vars (see
  `samba_service/config.py`).
- **`samba-server.spec`** — the PyInstaller spec (onedir). `collect_all`s the
  packages that load submodules/data by string at runtime (pyomo, oemof, pvlib,
  samba, samba_service) and pins uvicorn's auto-selected submodules.

## Build

```bash
uv sync --all-extras        # installs the `packaging` extra (pyinstaller)
just package-server         # → packaging/dist/samba-server/ (gitignored)
```

## Run

```bash
SAMBA_PORT=8000 SAMBA_DATA_DIR=./examples SAMBA_SOLVER=appsi_highs \
  packaging/dist/samba-server/samba-server
# then: curl http://127.0.0.1:8000/health
```

## Spike result (#63) — go/no-go: **GO**

Verified on **Linux x86_64, Python 3.13**:

| Metric | Result |
|---|---|
| Builds via committed spec | ✅ `just package-server` |
| Cold start to first `/health` 200 | **~1.5 s** |
| `/health` solver status | `appsi_highs`, `solver_ready: true` |
| Real scenario solve (`examples/base_scenario.yaml`) | ✅ `completed` in **~30 s**, 58 KPIs, 5 sizing rows |
| Bundle size (onedir, untrimmed) | **~439 MB** |

The solve runs the in-process `appsi_highs` (Pyomo APPSI + `highspy` wheel) — **no
external solver binary** is bundled or required.

## Tauri integration (#64)

The desktop app bundles the **onedir** as a Tauri resource and launches the inner
binary as a child process (not Tauri's onefile `externalBin`/sidecar API — keeps
the ~1.5 s cold start, no per-launch unpack).

- **`bundle.resources`** in `tauri.conf.json` ships `binaries/samba-server` with
  the app; at runtime `samba_process.rs` resolves
  `<resource_dir>/binaries/samba-server/samba-server`.
- **Staging:** `just stage-backend` builds the binary and copies it to
  `ui/src-tauri/binaries/samba-server` (gitignored) so `tauri build`/`dev` can
  bundle it. CI (#65) does this per-OS before `tauri build`.
- **Dev override:** set `SAMBA_SERVER_BIN=<path to samba-server>` to point the app
  at a binary directly, skipping resource resolution (Tauri does not copy bundle
  resources in `tauri dev`).
- **Config:** the app passes `SAMBA_PORT` (a free loopback port), `SAMBA_SOLVER`,
  CORS, and a writable `SAMBA_RUN_DIR`/`SAMBA_DATA_DIR` under the app's local-data
  dir, then blocks on `/health` before showing the UI. The backend is killed on
  window close (`Destroyed` event) and on `SambaProcess` drop.

Verified on Linux x86_64 (`tauri dev`): the app spawns the backend as its child,
`/health` returns `solver_ready: true`, and a graceful window close leaves **no
orphaned backend**.

## Constraints

- **Solver: `appsi_highs` only.** The frozen binary bundles the in-process HiGHS
  solver (`highspy`). Other Pyomo solvers (`cbc`, `glpk`, `gurobi`, ...) shell out
  to external executables that are **not** bundled — setting `SAMBA_SOLVER` to one
  of those will fail at runtime. The sidecar must keep `appsi_highs`.

## Known caveats / follow-ups

- **Size (~439 MB)** is untrimmed onedir. Trimming (excludes, UPX, onefile) is a
  later optimization, not needed to prove viability. Tracked under the per-OS
  matrix work.
- **onedir vs onefile** — onedir here (faster start, easy to inspect). The Tauri
  sidecar can use either; decide during sidecar wiring (#64).
- **Per-OS** — only Linux x86_64 is proven here. macOS (2 arches) + Windows are
  the build-matrix slice (#65); each re-runs the "does it solve?" check.
- PyInstaller `warn-*.txt` lists attribute-level false positives (e.g.
  `pydantic.BaseModel`); the runtime solve supersedes them.
