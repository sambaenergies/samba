# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""samba_service.auth -- API key authentication dependency for FastAPI.

Usage
-----

Protect any router or endpoint by adding this as a dependency::

    from fastapi import Security
    from samba_service.auth import verify_api_key

    @router.post("/my-endpoint", dependencies=[Security(verify_api_key)])
    async def my_endpoint() -> dict:
        ...

When ''SAMBA_API_KEY'' is unset (default), all requests pass without
authentication -- suitable for localhost or trusted-network deployments.

When ''SAMBA_API_KEY'' is set, every protected request must carry a
matching ''X-API-Key'' header; requests without it, or with a wrong
value, receive HTTP 401.
"""

from __future__ import annotations

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from samba_service.config import config

#: OpenAPI security scheme name -- appears in /docs Authorize dialog.
_API_KEY_SCHEME = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    x_api_key: str | None = Security(_API_KEY_SCHEME),
) -> None:
    """FastAPI Security dependency that validates the ''X-API-Key'' header.

    Parameters
    ----------
    x_api_key:
        Value of the ''X-API-Key'' request header (''None'' when absent).

    Raises
    ------
    HTTPException (401)
        When ''config.api_key'' is set and the header is missing or wrong.
    """
    if config.api_key is None:
        # No auth enforced -- trusted-network mode.
        return
    if x_api_key != config.api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Supply X-API-Key header.",
        )
