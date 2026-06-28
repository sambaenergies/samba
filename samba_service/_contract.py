# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Single source of truth for the SAMBA service API and contract versions.

Three independent version axes — keep them straight; a consumer must key
compatibility off the right one:

- **samba-core package version** (``samba._version.__version__``, e.g. ``5.3.1``)
  — the Python distribution/release version. Reported on ``/health`` as
  ``version`` for display only. Never key API compatibility off it.
- **API version** (:data:`API_VERSION`, e.g. ``1.0.0``) — SemVer of the HTTP
  surface (routes, request/response shapes, status codes). This is the FastAPI
  ``info.version`` and the value an external client should check for
  compatibility.
- **Contract version** (:data:`CONTRACT_VERSION`, e.g. ``1.0``) — the version of
  the published data/schema contract (OpenAPI document + companion JSON Schemas)
  that consumers generate types from. Mirrors the precedent
  :data:`samba._kpi_contract.KPI_CONTRACT_VERSION`.

URL namespace vs API version
----------------------------
The router is mounted under ``/api/v1`` — a *coarse* URL routing namespace,
bumped only on a breaking restructure (``/api/v1`` → ``/api/v2``).
:data:`API_VERSION` carries the *fine-grained* SemVer within that namespace, so
its **major matches the namespace**: ``/api/v1`` ⇔ ``API_VERSION`` ``1.x.y``.
Minor/patch API changes move :data:`API_VERSION` without touching the namespace.
(The OpenAPI *spec* version — ``3.1.0`` — is a third, unrelated number owned by
FastAPI, not configured here.)
"""

from __future__ import annotations

#: SemVer of the HTTP API surface; also FastAPI ``info.version``. Major matches
#: the ``/api/vN`` URL namespace.
API_VERSION = "1.0.0"

#: Version of the published data/schema contract (OpenAPI + companion schemas).
CONTRACT_VERSION = "1.0"

#: Stable, advertised feature flags an external client can branch on. Keep this
#: a small fixed list; add entries only when a genuinely new capability ships.
CAPABILITIES: list[str] = ["async_jobs", "artifacts", "validate", "auth_optional"]
