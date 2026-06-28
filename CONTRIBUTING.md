# Contributing to SAMBA

Thank you for your interest in contributing!

See [`docs/`](docs/) for user and developer documentation (architecture, domain model, results contract, scenario reference).

## Development Setup

SAMBA uses [uv](https://docs.astral.sh/uv/) for environment and dependency
management.

```bash
git clone https://github.com/sambaenergies/samba.git
cd samba
uv sync --all-extras       # creates .venv with dev group + cli + service extras
uv run pre-commit install
```

`uv sync` creates and manages the project virtual environment in `.venv` from the
committed `uv.lock`, giving every contributor a reproducible environment. Prefix
commands with `uv run` (e.g. `uv run pytest`) to execute them inside it.

If you have [`just`](https://github.com/casey/just) installed, the common tasks are
wrapped as recipes — run `just --list`.

## Dependency Lockfile

The pinned, cross-platform lockfile is committed at `uv.lock`. Regenerate it after
adding or removing a dependency in `pyproject.toml`:

```bash
uv lock          # or: just lock
git add uv.lock
```

## Running Tests

```bash
uv run pytest          # or: just test
```

## Running Golden Scenario Regressions

Golden benchmarks are excluded from the default `pytest` run (they take ~15 min).  Run them manually:

```bash
uv run pytest tests/goldens/ -m benchmark --tb=short -q    # or: just goldens
```

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting, and [Mypy](https://mypy.readthedocs.io/) for type checking.

```bash
uv run ruff check .
uv run mypy samba/
# or run the full CI-equivalent check:
just check
```
