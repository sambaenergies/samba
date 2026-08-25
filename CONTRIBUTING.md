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

## Docs

User and developer documentation lives in `docs/` and is built with
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).

```bash
just docs-build    # mkdocs build --strict — what CI runs
just docs-serve    # live-reload preview on http://127.0.0.1:8000
```

`--strict` turns every warning into a failure, and `mkdocs.yml` additionally
promotes MkDocs' INFO-level diagnostics (missing heading anchors, links that
leave the docs tree, pages absent from `nav`) to warnings. In practice:

- **Adding a page** means adding it to `nav` in `mkdocs.yml`, or the build fails.
- **Linking to a file outside `docs/`** (`../CHANGELOG.md`, `../Dockerfile`) fails
  — those files are not part of the site. Use a full
  `https://github.com/sambaenergies/samba/blob/main/…` URL instead.
- **Linking to a `#heading-anchor`** that does not exist fails.

`mkdocs.yml` does not publish anything. The public site
(`docs.sambaenergies.com`) is built by the separate `sambaenergies/docs` repo,
which aggregates `docs/` from every org repo; this config is what lets breakage
be caught here, at the source. See epic #56.

## Service contract (OpenAPI + schemas)

The backend Pydantic models are the single source of truth for every shape that
crosses to the UI. Two generated, committed, drift-gated artifacts make up the
published contract:

- **`openapi.json`** (repo root) — the HTTP API document, from `just openapi`.
- **`schemas/*.schema.json`** — JSON Schema for the downloadable result artifacts
  (kpis/economics/sizing/dispatch) and the request/response envelopes, from
  `just schemas`. The UI generates its TypeScript from these (`npm run gen:types`).

After any change to a service route or model, regenerate and commit both:

```bash
just schemas && just openapi    # then commit the diffs
```

`just check` fails if either is stale (`git diff --exit-code`), and
`tests/unit/test_{schema,openapi}_export.py` fail in `just test` independently of
git. Both exporters require the service extras (`uv sync --all-extras`) so FastAPI
is importable, and emit **alphabetically key-sorted** JSON for byte-stable output.
A FastAPI/Pydantic upgrade can produce a non-substantive `openapi.json` diff — just
regenerate and commit it.

### Version axes

Three independent versions, defined authoritatively in
[`samba_service/_contract.py`](samba_service/_contract.py) (including the
`/api/v1` URL-namespace-vs-`info.version` rule — do not re-decide it elsewhere):

| Version | Source | Bumps when |
|---|---|---|
| **samba-core** SemVer (e.g. `5.3.1`) | `samba/_version.py` | any released code change; display-only on `/health`, never key compatibility off it |
| **API version** (`API_VERSION`, e.g. `1.0.0`) | `_contract.py` → FastAPI `info.version` | the HTTP surface changes (routes / request-response shapes / status codes); major matches the `/api/vN` namespace |
| **Contract version** (`CONTRACT_VERSION`, e.g. `1.0`) | `_contract.py` | the published contract bundle (openapi + schemas) changes in a way consumers must track |
| OpenAPI spec (`3.1.0`) | owned by FastAPI | — (not configured here) |

### Where the release version lives

`samba/_version.py` is the **only** place to edit it. `pyproject.toml` derives it
(`dynamic = ["version"]` + `[tool.hatch.version]`), so packaging can never drift.

Two files are static and cannot derive it, so they are **gated instead of
hand-audited** by `tests/unit/test_version_consistency.py`:

- `CITATION.cff` — `version` and `date-released`
- `CHANGELOG.md` — the most recent release heading

Bump `samba/_version.py`, run `just test`, and the gate names anything else that
needs updating. Don't keep a manual list of version locations — add a case to
that test instead, so a missed spot fails CI rather than shipping stale.

> Editable installs cache bytecode by `(mtime, size)`. Two version strings of
> equal length written in the same second can leave a stale `.pyc`; if a version
> change seems not to take effect, clear `__pycache__`.

## Branch protection & CI gates

`main` requires a **single** status check (GitHub repo setting, not in-repo)
before a PR can merge: **`CI gate`**. It is an aggregator that `needs:` every
job below and passes only when each one **succeeded or was skipped** — so it is
the one context branch protection points at, and it always reports (it has no
path filter). The jobs it gates:

- **`Check (ruff + mypy + schema drift)`**, **`Test (Python 3.11–3.14)`** — the
  Python gate.
- **`UI (just ui-check)`** — the **same-tree** UI gate: `gen:types` drift +
  eslint + vue-tsc + vitest, relating `ui/contract/` to the backend export.
- **`UI external-consumer build (isolation)`** — builds `ui/` from a copy with no
  Python tree or repo-root `schemas/` above it, proving self-containment, plus a
  reach-through guard.
- **`UI compatibility (baseline UI vs PR contract)`** — typechecks the base
  branch's UI against the PR's contract, catching a backend change that breaks a
  shape the UI consumes.
- **`Contract breaking-change check`** — oasdiff fails a breaking `openapi.json`
  change unless `CONTRACT_VERSION` major was bumped.
- **`Docs (mkdocs --strict)`** — builds `docs/` with every link, nav entry and
  heading anchor validated. See [Docs](#docs).

The `UI (just ui-check)` and `UI external-consumer build` jobs are **both** kept:
the former is the same-tree drift gate, the latter proves self-containment — they
verify different things. The compatibility and breaking-change jobs are
**PR-only** (they need a base ref); if a GitHub merge queue is ever adopted, add
`|| github.event_name == 'merge_group'` to their `if:` so they still run in the
queue.

**Docs-only path filtering.** A `changes` job detects when a PR touches only docs
(`**.md`, `docs/**`, `LICENSE`); when so, the heavy jobs **skip** (saving the
matrix) while `CI gate` still runs and passes — because branch protection requires
only `CI gate`, the docs PR merges quickly. Adding a *new* required check means
adding it to `CI gate`'s `needs:` list, not to the branch-protection settings.

`Docs (mkdocs --strict)` is the **inverse** filter — the one job a docs-only PR
still runs. It also fires on `mkdocs.yml`, `pyproject.toml`, `uv.lock` and the
`justfile`, so a dependency bump to a breaking MkDocs/Material release cannot
skip the job that would catch it.

> **Out of scope (deferred):** actual UI extraction and the desktop/registry product boundary are catalogued in [docs/deferred-extraction.md](docs/deferred-extraction.md).
