# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for the v4 NSRDB weather fetch (network mocked; offline-safe)."""

from __future__ import annotations

import pathlib

import pytest

from samba.weather import fetch
from samba.weather.fetch import WeatherFetchError, fetch_weather, nsrdb_cache_file

EXAMPLES_CONTENT = pathlib.Path(__file__).parent.parent.parent / "examples" / "content"
METEO_CSV = EXAMPLES_CONTENT / "weather_sf_2019.csv"
_SAMPLE_NSRDB = METEO_CSV.read_text(encoding="utf-8")


class TestCachePath:
    def test_cache_filename_is_deterministic(self, tmp_path: pathlib.Path) -> None:
        p = nsrdb_cache_file(37.77, -122.42, 2019, tmp_path)
        assert p == tmp_path / "nsrdb_37.7700_-122.4200_2019.csv"


class TestFetchWeather:
    def test_fetch_parses_to_weatherdata(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def fake_http_get(url: str, params: dict) -> str:  # type: ignore[type-arg]
            calls.append(url)
            return _SAMPLE_NSRDB

        monkeypatch.setattr(fetch, "_http_get", fake_http_get)
        wd = fetch_weather(37.77, -122.42, 2019, api_key="k", email="e@x.com", cache_dir=tmp_path)
        assert len(wd.timestamp) == 8760
        assert len(calls) == 1  # network hit on miss
        assert nsrdb_cache_file(37.77, -122.42, 2019, tmp_path).exists()

    def test_cache_hit_skips_network(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def fake_http_get(url: str, params: dict) -> str:  # type: ignore[type-arg]
            calls.append(url)
            return _SAMPLE_NSRDB

        monkeypatch.setattr(fetch, "_http_get", fake_http_get)
        # First call populates the cache; second must not call the network.
        fetch_weather(37.77, -122.42, 2019, api_key="k", email="e@x.com", cache_dir=tmp_path)
        fetch_weather(37.77, -122.42, 2019, api_key="k", email="e@x.com", cache_dir=tmp_path)
        assert len(calls) == 1

    def test_missing_credentials_raises(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NREL_API_KEY", raising=False)
        monkeypatch.delenv("NREL_API_EMAIL", raising=False)
        with pytest.raises(WeatherFetchError, match="API key"):
            fetch_weather(37.77, -122.42, 2019, cache_dir=tmp_path)

    def test_unsupported_source_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(WeatherFetchError, match="unsupported"):
            fetch_weather(37.77, -122.42, 2019, source="pvgis", cache_dir=tmp_path)

    def test_http_failure_wrapped(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(url: str, params: dict) -> str:  # type: ignore[type-arg]
            raise OSError("network down")

        monkeypatch.setattr(fetch, "_http_get", boom)
        with pytest.raises(WeatherFetchError, match="fetch failed"):
            fetch_weather(37.77, -122.42, 2019, api_key="k", email="e@x.com", cache_dir=tmp_path)
