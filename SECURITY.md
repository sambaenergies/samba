# Security Policy

## Supported versions

SAMBA is released on a rolling basis; security fixes land on the latest minor
release line. Please use the most recent `5.x` release.

| Version | Supported |
|---|---|
| latest `5.x` | ✅ |
| older | ❌ (please upgrade) |

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report privately via GitHub's **"Report a vulnerability"** button under the
repository's **Security** tab (Private Vulnerability Reporting). Include:

- a description of the issue and its impact,
- steps to reproduce (a minimal scenario YAML or request, if applicable),
- the affected version (`samba info` output helps).

We aim to acknowledge reports within a few days and to coordinate a fix and
disclosure timeline with you.

## Scope notes

- **Solver / scenario input:** SAMBA solves user-supplied scenario YAML locally.
  Treat scenario files from untrusted sources as untrusted input.
- **REST service (`samba serve`):** binds to `127.0.0.1` by default and supports
  optional API-key auth (`--api-key` / `SAMBA_API_KEY`). Do not expose it on an
  untrusted network without authentication and a TLS-terminating proxy.

## Desktop auto-updater key management (forward-looking)

The native desktop packaging (planning phase U4) will use Tauri's updater, signed
with an **Ed25519** keypair. When that ships:

- the **private** signing key is stored only as a CI secret
  (`TAURI_SIGNING_PRIVATE_KEY`) and is **never committed** to the repository;
- the **public** key lives in `ui/src-tauri/tauri.conf.json`;
- the private key is **unrecoverable if lost** — a new keypair must be generated
  and the public key updated, after which existing installs no longer receive
  auto-updates and must be re-installed once. Rotate deliberately and back up the
  key securely.
