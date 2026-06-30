# SAMBA developer tasks — uv-based.
# Run `just --list` to see available recipes.

# Install all dependencies (dev group + cli + service extras) into .venv
setup:
    uv sync --all-extras

# Format code (ruff format + autofix lint)
fmt:
    uv run ruff format .
    uv run ruff check --fix .

# Lint only (no changes)
lint:
    uv run ruff check .

# Export JSON Schema for all cross-boundary contracts (run after changing models)
schemas:
    uv run python scripts/export_schemas.py

# Export the deterministic OpenAPI document (run after changing service routes/models)
openapi:
    uv run python scripts/export_openapi.py

# Vendor the committed contract (schemas + openapi) into ui/contract/ for the UI build
contract-sync:
    uv run python scripts/sync_ui_contract.py

# THE mandated regen after any contract change: schemas -> openapi -> vendor -> UI types.
# Run this (not the individual recipes) so all drift-gated copies update atomically.
contract: schemas openapi contract-sync
    cd ui && npm run gen:types

# Regenerate all logo derivatives (favicon, app icons, mono variants) from the source SVG
logo:
    uv run --with pillow python scripts/gen_logo_assets.py

# CI-equivalent: format check + lint + type check + schema drift gate
check:
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy samba/
    uv run mypy samba_service/
    uv run python scripts/export_schemas.py
    git diff --exit-code -- schemas
    uv run python scripts/export_openapi.py
    git diff --exit-code -- openapi.json
    uv run python scripts/sync_ui_contract.py
    git diff --exit-code -- ui/contract

# UI checks: regenerate types from schemas (drift gate), lint, type-check, unit tests
ui-check:
    cd ui && npm run gen:types
    git diff --exit-code -- ui/src/api/generated
    cd ui && npm run lint
    cd ui && npx vue-tsc --noEmit
    cd ui && npm run test

# Run the fast test suite (golden benchmarks deselected)
test:
    uv run pytest

# Run golden scenario benchmarks (slow, ~15 min)
goldens:
    uv run pytest tests/goldens/ -m benchmark --tb=short -q

# Regenerate the lockfile after changing dependencies
lock:
    uv lock

# Freeze the backend (samba serve) into a standalone binary for the Tauri
# sidecar. Output: packaging/dist/samba-server/ (gitignored). Needs the
# packaging extra: `uv sync --all-extras`.
package-server:
    uv run pyinstaller --noconfirm --clean \
      --distpath packaging/dist --workpath packaging/build \
      packaging/samba-server.spec
