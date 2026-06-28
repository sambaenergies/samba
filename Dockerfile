# SAMBA REST service image (v4) -- uv-based.
#
#   docker build -t samba-service .
#   docker run -p 8000:8000 -v "$PWD/data:/data" samba-service
#
# The container runs the FastAPI service (samba_service.app:app) with the
# SQLite-backed persistent job store enabled, writing results under /data.
FROM python:3.12-slim

# uv from the official distroless image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cached layer) using the committed lockfile.
COPY pyproject.toml uv.lock README.md ./
COPY samba ./samba
COPY samba_cli ./samba_cli
COPY samba_service ./samba_service

# Production deps only: core + the `service` and `cli` extras, no dev group.
RUN uv sync --frozen --no-dev --extra service --extra cli

ENV PATH="/app/.venv/bin:${PATH}" \
    SAMBA_HOST=0.0.0.0 \
    SAMBA_PORT=8000 \
    SAMBA_RUN_DIR=/data/results \
    SAMBA_DATA_DIR=/data \
    SAMBA_PERSIST_JOBS=1

EXPOSE 8000
VOLUME ["/data"]

# Use the project venv's uvicorn to serve the app.
CMD ["uvicorn", "samba_service.app:app", "--host", "0.0.0.0", "--port", "8000"]
