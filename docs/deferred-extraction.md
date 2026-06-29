# Deferred: actual UI extraction & product-boundary work

Status: **OUT OF SCOPE** for the co-located "virtual split" (epic #25). Recorded
here so it is tracked, not silently dropped.

The virtual split made `ui/` build and operate **as if** it lived in a separate
repository — it consumes a vendored, deterministic, isolation-enforced contract
(`ui/contract/`) and never reaches into the Python tree. None of the items below
were needed for that, and each is only worth doing when an **actual extraction**
(or a hosted/remote-backend product) is decided. They are listed with their open
questions so the decision is informed when it is made.

## What makes a future extraction safe (in-scope, already shipped)

These are the prerequisites the virtual split delivered, and the reason the swaps
below can be done later without architectural upheaval:

- **Runtime compatibility check** — `/health` exposes `api_version`,
  `contract_version`, and `capabilities` (`samba_service/_contract.py`), and the
  UI surfaces a distinct `incompatible` state on an API-major mismatch vs the
  vendored contract (`ui/src/stores/connection.ts`).
- **Vendored, deterministic, gated contract** — committed `openapi.json` +
  `schemas/`, vendored into `ui/contract/`, byte-deterministic across runs and
  Python versions, with drift gates, an external-consumer isolation build, and a
  backend↔baseline-UI compatibility + breaking-change gate
  (issues #31, #32, #33, #35, #36).

## Deferred — contract distribution

### Packaged versioned contract bundle

Moved here from the de-scoped bundle slice. Would add `scripts/build_contract_bundle.py`,
a `samba-contracts-<version>.tar.gz`, a `manifest.json` with per-file `sha256` +
`samba_version` + `git_sha`, a `release.yml` asset attachment, and a
`workflow_dispatch` dry-run.

**Verified reason it was de-scoped:** nothing in-scope consumes a release
asset — `ui/contract/` and the compat gate sync directly from the *plain
exporters* (`export_schemas` / `export_openapi`) and the committed
`openapi.json`/`schemas/`. A committed, `sha`/`git_sha`-bearing manifest is also
self-defeating against a same-tree `git diff --exit-code` drift gate (it would
change on every commit). This bundle is the artifact the future **registry
channel** below would publish — build it only when that channel is built.

### Registry-published contract package

Publish the bundle to npm / GitHub Packages (e.g. `@sambaenergies/samba-contract`),
with dual PyPI + npm release wiring, npm provenance / `.npmrc` / registry auth, and
exact version pinning in `ui/package.json` (with `package-lock` integrity).

*Open question:* the virtual split instead vendors into `ui/contract/`; a registry
package only pays off once the UI is genuinely a separate repo/consumer.

## Deferred — desktop (Tauri) product boundary

### Backend PATH coupling

`ui/src-tauri/src/samba_process.rs` spawns `Command::new("samba").arg("serve")` —
i.e. it expects the `samba` executable on `PATH`.

*Open question:* how does the desktop app locate/launch the backend when `samba`
is not on `PATH` — bundle it, require a separate `pip install samba-core[service]`,
or connect to a hosted service?

### Bundled sidecar / `externalBin`

`tauri.conf.json` has **no** `externalBin`/sidecar key — the backend is not packaged
with the app. Bundling a platform-specific service binary is deferred.

### Installer signing / notarization + auto-updater

Absent from `tauri.conf.json`. Code signing, notarization, and an auto-updater
channel are required for real public desktop distribution.

### Remote-backend CSP

`tauri.conf.json` pins `connect-src` to `http://127.0.0.1:*`. A remote/hosted
backend would require relaxing it (and re-evaluating the security posture).

## Deferred — UI as a separately-delivered product

`samba-ui` package name, independent UI versioning, and its own release tag
(`ui-vX.Y.Z`) — only meaningful once the UI ships on its own cadence / as its own
artifact, i.e. an actual extraction.
