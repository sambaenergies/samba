# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""samba_service.config -- Runtime configuration for the SAMBA REST service.

Values are read from environment variables at import time.  Override them
before importing ''samba_service.app'' in tests or other code that needs
non-default settings.

Environment variables
---------------------
SAMBA_RUN_DIR        Base directory where run artifacts are written.
                     Default: ''results''.
SAMBA_DATA_DIR       Base directory for resolving relative CSV paths in scenarios.
                     Default: current working directory at service start.
SAMBA_HOST           Bind host for ''samba serve''.  Default: ''127.0.0.1''.
SAMBA_PORT           Bind port for ''samba serve''.  Default: ''8000''.
SAMBA_SOLVER         Pyomo solver name.  Default: ''appsi_highs''.
SAMBA_TIME_LIMIT     Solver wall-clock time limit (seconds).  Default: ''600''.
SAMBA_API_KEY        Optional API key for request authentication.  When set,
                     all non-health endpoints require the ''X-API-Key'' header
                     to match this value.  When unset (default), no auth is
                     enforced (trusted-network mode).
SAMBA_CORS_ORIGINS   Comma-separated list of allowed CORS origins.
                     Default: ''*'' (allow all origins).
SAMBA_MAX_CONCURRENT Maximum number of simultaneous solve jobs.  Default: ''4''.
SAMBA_JOB_TTL_HOURS  How long (hours) to retain completed/failed job metadata
                     in the in-process store.  Default: ''24.0''.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServiceConfig:
    """Mutable configuration container for the SAMBA service.

    Attributes
    ----------
    run_base_dir:
        Parent directory under which per-run result subdirectories are created.
    data_dir:
        Base directory used to resolve relative ''csv_path'' values declared
        inside a scenario.  Set this to the directory that contains your CSV
        data files when hosting the service.
    host:
        Bind host passed to ''uvicorn'' by ''samba serve''.
    port:
        Bind port passed to ''uvicorn'' by ''samba serve''.
    solver:
        LP/MILP solver name (Pyomo ''SolverFactory'' key).
    time_limit_s:
        Maximum solver wall-clock time in seconds.
    api_key:
        Optional API key string.  ''None'' means no authentication is
        enforced.  When set, all non-health requests must carry a matching
        ''X-API-Key'' HTTP header.
    cors_origins:
        List of allowed CORS origins.  ''["*"]'' allows all (default).
    max_concurrent:
        Maximum number of simultaneous background solve jobs kept in the
        :class:'~concurrent.futures.ThreadPoolExecutor'.
    job_ttl_hours:
        Number of hours to retain completed/failed job records in the
        job store before they are eligible for eviction.
    persist_jobs:
        When ''True'', use a SQLite-backed job store (``run_base_dir/jobs.db``)
        so job records survive a service restart.  Default ''False'' (in-memory).
    """

    run_base_dir: Path = field(default_factory=lambda: Path("results"))
    data_dir: Path = field(default_factory=Path.cwd)
    host: str = "127.0.0.1"
    port: int = 8000
    solver: str = "appsi_highs"
    time_limit_s: int = 600
    api_key: str | None = None
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    max_concurrent: int = 4
    job_ttl_hours: float = 24.0
    persist_jobs: bool = False

    def __post_init__(self) -> None:
        if v := os.getenv("SAMBA_RUN_DIR"):
            self.run_base_dir = Path(v)
        if v := os.getenv("SAMBA_DATA_DIR"):
            self.data_dir = Path(v)
        if v := os.getenv("SAMBA_HOST"):
            self.host = v
        if v := os.getenv("SAMBA_PORT"):
            self.port = int(v)
        if v := os.getenv("SAMBA_SOLVER"):
            self.solver = v
        if v := os.getenv("SAMBA_TIME_LIMIT"):
            self.time_limit_s = int(v)
        if v := os.getenv("SAMBA_API_KEY"):
            self.api_key = v
        if v := os.getenv("SAMBA_CORS_ORIGINS"):
            self.cors_origins = [o.strip() for o in v.split(",") if o.strip()]
        if v := os.getenv("SAMBA_MAX_CONCURRENT"):
            self.max_concurrent = int(v)
        if v := os.getenv("SAMBA_JOB_TTL_HOURS"):
            self.job_ttl_hours = float(v)
        if v := os.getenv("SAMBA_PERSIST_JOBS"):
            self.persist_jobs = v.strip().lower() in ("1", "true", "yes", "on")


#: Module-level singleton.  Mutate this object to change service behaviour at
#: runtime (e.g. inside the ''samba serve'' CLI command or in test fixtures).
config = ServiceConfig()
