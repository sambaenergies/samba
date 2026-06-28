# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""SQLite-backed persistent job store (v4 Phase 28).

A drop-in replacement for :class:`samba_service.jobs.JobStore` with the identical
public interface (``create``/``get``/``update``/``remove``/``list_all``/
``expire_old``).  Job records survive a service restart, so a client polling a
``run_id`` after a redeploy / pod eviction still gets its status and artifacts.

The default in-memory store is used unless ``SAMBA_PERSIST_JOBS`` is enabled
(see :mod:`samba_service.config`).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from samba_service.jobs import Job, JobStatus, JobStore

__all__ = ["PersistentJobStore"]

_COLUMNS = (
    "run_id",
    "status",
    "submitted_at",
    "started_at",
    "completed_at",
    "run_dir",
    "error",
    "kpis",
    "sizing",
)


def _dt_to_str(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _str_to_dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class PersistentJobStore(JobStore):
    """Thread-safe SQLite job store with the same interface as ``JobStore``."""

    def __init__(self, db_path: Path | str) -> None:
        super().__init__()
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the ThreadPoolExecutor workers and the request
        # threads share this connection; all access is serialised by self._lock.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    run_id       TEXT PRIMARY KEY,
                    status       TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    started_at   TEXT,
                    completed_at TEXT,
                    run_dir      TEXT,
                    error        TEXT,
                    kpis         TEXT,
                    sizing       TEXT
                )
                """
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Row <-> Job serialisation
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            run_id=row["run_id"],
            status=JobStatus(row["status"]),
            submitted_at=_str_to_dt(row["submitted_at"]) or datetime.now(UTC),
            started_at=_str_to_dt(row["started_at"]),
            completed_at=_str_to_dt(row["completed_at"]),
            run_dir=Path(row["run_dir"]) if row["run_dir"] else None,
            error=row["error"],
            kpis=json.loads(row["kpis"]) if row["kpis"] else None,
            sizing=json.loads(row["sizing"]) if row["sizing"] else None,
        )

    @staticmethod
    def _job_to_params(job: Job) -> dict[str, Any]:
        return {
            "run_id": job.run_id,
            "status": job.status.value,
            "submitted_at": _dt_to_str(job.submitted_at),
            "started_at": _dt_to_str(job.started_at),
            "completed_at": _dt_to_str(job.completed_at),
            "run_dir": str(job.run_dir) if job.run_dir is not None else None,
            "error": job.error,
            "kpis": json.dumps(job.kpis) if job.kpis is not None else None,
            "sizing": json.dumps(job.sizing) if job.sizing is not None else None,
        }

    def _upsert(self, job: Job) -> None:
        cols = ", ".join(_COLUMNS)
        placeholders = ", ".join(f":{c}" for c in _COLUMNS)
        self._conn.execute(
            f"INSERT OR REPLACE INTO jobs ({cols}) VALUES ({placeholders})",
            self._job_to_params(job),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API (mirrors JobStore)
    # ------------------------------------------------------------------

    def create(self, run_id: str) -> Job:
        job = Job(run_id=run_id)
        with self._lock:
            self._upsert(job)
        return job

    def get(self, run_id: str) -> Job | None:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM jobs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
        return self._row_to_job(row) if row is not None else None

    def update(self, run_id: str, **kwargs: Any) -> None:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM jobs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if row is None:
                return  # silently ignore unknown / expired run_id
            job = self._row_to_job(row)
            for k, v in kwargs.items():
                setattr(job, k, v)
            self._upsert(job)

    def remove(self, run_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM jobs WHERE run_id = ?", (run_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def list_all(self, status_filter: str | None = None) -> list[Job]:
        self.expire_old()
        with self._lock:
            rows = self._conn.execute("SELECT * FROM jobs").fetchall()
        jobs = [self._row_to_job(r) for r in rows]
        if status_filter is not None:
            jobs = [j for j in jobs if j.status.value == status_filter]
        jobs.sort(key=lambda j: j.submitted_at, reverse=True)
        return jobs

    def expire_old(self, ttl_hours: float | None = None) -> int:
        from samba_service.config import config

        ttl = ttl_hours if ttl_hours is not None else config.job_ttl_hours
        now = datetime.now(UTC)
        with self._lock:
            rows = self._conn.execute(
                "SELECT run_id, status, completed_at FROM jobs WHERE completed_at IS NOT NULL"
            ).fetchall()
            evict: list[str] = []
            for row in rows:
                if row["status"] not in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
                    continue
                completed = _str_to_dt(row["completed_at"])
                if completed is None:
                    continue
                if (now - completed).total_seconds() / 3600.0 > ttl:
                    evict.append(row["run_id"])
            for rid in evict:
                self._conn.execute("DELETE FROM jobs WHERE run_id = ?", (rid,))
            if evict:
                self._conn.commit()
        return len(evict)

    def close(self) -> None:
        """Close the underlying SQLite connection (for tests / shutdown)."""
        with self._lock:
            self._conn.close()
