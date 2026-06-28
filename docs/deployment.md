# Deploying the SAMBA REST Service

The `samba_service` package is a FastAPI app (`samba_service.app:app`) that runs
solves as background jobs and serves their artifacts. This guide covers running it
in production.

## Quick start (Docker)

```bash
docker build -t samba-service .
docker run -p 8000:8000 -v "$PWD/data:/data" samba-service
# API now at http://localhost:8000  (docs at /docs)
```

The image (uv-based, see [`Dockerfile`](../Dockerfile)) enables the **persistent
job store** and writes results under `/data`, which is exposed as a volume so jobs
and artifacts survive container restarts.

## Configuration

All settings are environment variables (see `samba_service/config.py`):

| Variable | Default | Purpose |
|---|---|---|
| `SAMBA_HOST` / `SAMBA_PORT` | `127.0.0.1` / `8000` | Bind address |
| `SAMBA_RUN_DIR` | `results` | Where per-run artifacts are written |
| `SAMBA_DATA_DIR` | cwd | Base dir for resolving scenario `csv_path`s |
| `SAMBA_API_KEY` | _(unset)_ | When set, all non-health routes require `X-API-Key` |
| `SAMBA_CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `SAMBA_MAX_CONCURRENT` | `4` | Max simultaneous background solves |
| `SAMBA_JOB_TTL_HOURS` | `24` | Retention before completed/failed jobs are evicted |
| `SAMBA_PERSIST_JOBS` | `false` | **Use the SQLite job store** (`SAMBA_RUN_DIR/jobs.db`) so jobs survive restart |

## Job persistence

By default the job store is **in-process and non-persistent** — job records (and
in-flight solves) are lost on restart, and polling a `run_id` afterwards returns
404. For any deployment with auto-restart (k8s eviction, redeploy, OOM), set
`SAMBA_PERSIST_JOBS=1` (the Docker image does this by default). Job metadata is
then stored in a SQLite database at `SAMBA_RUN_DIR/jobs.db`; artifacts live under
`SAMBA_RUN_DIR`. Mount both on a persistent volume.

> In-flight (RUNNING) jobs are not resumed after a crash — only their records
> persist; re-submit interrupted solves.

## Running without Docker

```bash
uv sync --all-extras
SAMBA_PERSIST_JOBS=1 uv run uvicorn samba_service.app:app --host 0.0.0.0 --port 8000
# or via the CLI:
SAMBA_PERSIST_JOBS=1 uv run samba serve
```

## Continuous integration

CI runs via GitHub Actions (`.github/workflows/`):

- **`ci.yml`** — on push / pull request: a backend matrix (Ubuntu + Windows ×
  Python 3.11–3.13) running ruff lint + format check, mypy, and the pytest suite
  (which includes the schema-export drift test); plus a **UI** job (generated-type
  drift gate, eslint, vue-tsc, vitest).
- **`goldens.yml`** — nightly (and on `samba/**` / `tests/goldens/**` changes):
  the golden-scenario benchmark suite.

Both are uv-based and cached.
