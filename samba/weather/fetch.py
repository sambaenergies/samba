# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Weather data ingestion from the NREL NSRDB API (v4 Phase 26).

Removes the manual-CSV barrier: given a latitude/longitude/year, fetch a year of
NSRDB data and return a :class:`~samba.weather.models.WeatherData`. The NSRDB API
returns data in the same NSRDB CSV format the local parser already reads, so the
fetched payload is cached as a CSV and parsed by :func:`read_nsrdb_csv` — one code
path for local and fetched data.

Network access is isolated behind :func:`_http_get` so tests mock it and CI stays
offline; results are cached on disk, so a second run for the same
(lat, lon, year) never hits the network.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from samba.weather.models import WeatherData
from samba.weather.nsrdb import read_nsrdb_csv

log = logging.getLogger(__name__)

__all__ = ["fetch_weather", "default_cache_dir", "nsrdb_cache_file", "WeatherFetchError"]

# NSRDB v2 download API (NLR Developer Network). PSM3 is deprecated; use the PSM4
# GOES v4 aggregated endpoint (the current default in pvlib's NSRDB client).
_NSRDB_ENDPOINT = (
    "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv"
)


class WeatherFetchError(RuntimeError):
    """Raised when a weather fetch cannot be completed."""


def default_cache_dir() -> Path:
    """Return the on-disk weather cache directory (``$SAMBA_WEATHER_CACHE`` or ~/.cache)."""
    env = os.getenv("SAMBA_WEATHER_CACHE")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "samba" / "weather"


def _http_get(url: str, params: dict[str, str]) -> str:
    """Perform an HTTP GET and return the response body as text.

    Isolated so tests can monkeypatch it; the real implementation uses urllib so
    there is no hard runtime dependency on ``requests``/``httpx``.
    """
    import urllib.parse
    import urllib.request

    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"
    log.info("Fetching weather from %s", url)
    with urllib.request.urlopen(full_url, timeout=60) as resp:  # noqa: S310 - fixed NREL host
        body: bytes = resp.read()
    return body.decode("utf-8")


def nsrdb_cache_file(
    latitude: float, longitude: float, year: int, cache_dir: Path | str | None = None
) -> Path:
    """Return the cache file path for a given site/year (without fetching)."""
    cdir = Path(cache_dir) if cache_dir is not None else default_cache_dir()
    return cdir / f"nsrdb_{latitude:.4f}_{longitude:.4f}_{year}.csv"


def fetch_weather(
    latitude: float,
    longitude: float,
    year: int,
    *,
    source: str = "nsrdb",
    api_key: str | None = None,
    email: str | None = None,
    cache_dir: Path | str | None = None,
) -> WeatherData:
    """Fetch (or load from cache) a year of weather for a site as ``WeatherData``.

    Parameters
    ----------
    latitude, longitude:
        Site coordinates [deg].
    year:
        Calendar year to fetch (a non-leap year is expected downstream).
    source:
        Currently only ``"nsrdb"`` (NREL Physical Solar Model 3).
    api_key, email:
        NREL API credentials; fall back to ``$NREL_API_KEY`` / ``$NREL_API_EMAIL``.
    cache_dir:
        Override the cache directory (default :func:`default_cache_dir`).

    Returns
    -------
    WeatherData
    """
    if source != "nsrdb":
        raise WeatherFetchError(f"unsupported weather source for fetch: {source!r}")

    cdir = Path(cache_dir) if cache_dir is not None else default_cache_dir()
    cache_file = nsrdb_cache_file(latitude, longitude, year, cdir)

    if cache_file.exists():
        log.info("Weather cache hit: %s", cache_file)
        return read_nsrdb_csv(cache_file)

    key = api_key or os.getenv("NREL_API_KEY")
    mail = email or os.getenv("NREL_API_EMAIL")
    if not key or not mail:
        raise WeatherFetchError(
            "NSRDB fetch requires an API key and email. Set weather.nsrdb_api_key / "
            "weather.nsrdb_email, or the NREL_API_KEY / NREL_API_EMAIL environment "
            "variables. Get a free key at https://developer.nlr.gov/signup/."
        )

    params = {
        "api_key": key,
        "email": mail,
        "wkt": f"POINT({longitude} {latitude})",
        "names": str(year),
        "attributes": "ghi,dhi,dni,air_temperature,wind_speed,surface_albedo",
        "interval": "60",
        "utc": "false",
        "leap_day": "false",
    }
    try:
        body = _http_get(_NSRDB_ENDPOINT, params)
    except Exception as exc:  # noqa: BLE001
        raise WeatherFetchError(f"NSRDB fetch failed: {exc}") from exc

    cdir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(body, encoding="utf-8")
    log.info("Cached fetched weather to %s", cache_file)
    return read_nsrdb_csv(cache_file)
