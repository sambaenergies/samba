# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""Unit tests for the v4 SQLite PersistentJobStore."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from samba_service.jobs import JobStatus
from samba_service.persistent_jobs import PersistentJobStore


def _store(tmp_path: Path) -> PersistentJobStore:
    return PersistentJobStore(tmp_path / "jobs.db")


class TestInterfaceParity:
    def test_create_and_get(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        job = store.create("run-1")
        assert job.run_id == "run-1"
        assert job.status == JobStatus.PENDING
        got = store.get("run-1")
        assert got is not None and got.run_id == "run-1"

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        assert _store(tmp_path).get("nope") is None

    def test_update_fields(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create("run-1")
        store.update(
            "run-1",
            status=JobStatus.COMPLETED,
            run_dir=Path("/tmp/out"),
            kpis={"npc": 123.0},
            sizing=[{"component": "pv", "capacity": 5.0}],
        )
        got = store.get("run-1")
        assert got is not None
        assert got.status == JobStatus.COMPLETED
        assert got.run_dir == Path("/tmp/out")
        assert got.kpis == {"npc": 123.0}
        assert got.sizing == [{"component": "pv", "capacity": 5.0}]

    def test_update_unknown_is_silent(self, tmp_path: Path) -> None:
        _store(tmp_path).update("ghost", status=JobStatus.FAILED)  # no raise

    def test_remove(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create("run-1")
        assert store.remove("run-1") is True
        assert store.remove("run-1") is False
        assert store.get("run-1") is None

    def test_list_all_sorted_and_filtered(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create("a")
        store.create("b")
        store.update("b", status=JobStatus.COMPLETED, completed_at=datetime.now(UTC))
        all_jobs = store.list_all()
        assert {j.run_id for j in all_jobs} == {"a", "b"}
        completed = store.list_all(status_filter="completed")
        assert [j.run_id for j in completed] == ["b"]


class TestPersistenceAcrossRestart:
    def test_job_survives_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "jobs.db"
        store1 = PersistentJobStore(db)
        store1.create("run-1")
        store1.update(
            "run-1",
            status=JobStatus.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            run_dir=Path("/tmp/run-1"),
            kpis={"npc": 42.0, "lcoe": 0.3},
            sizing=[{"component": "battery", "capacity": 10.0}],
        )
        store1.close()

        # Simulate a service restart: a fresh store on the same DB file.
        store2 = PersistentJobStore(db)
        got = store2.get("run-1")
        assert got is not None
        assert got.status == JobStatus.COMPLETED
        assert got.run_dir == Path("/tmp/run-1")
        assert got.kpis == {"npc": 42.0, "lcoe": 0.3}
        assert got.sizing == [{"component": "battery", "capacity": 10.0}]
        assert got.started_at is not None and got.completed_at is not None


class TestExpiry:
    def test_expire_old_removes_stale_completed(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create("old")
        store.update(
            "old",
            status=JobStatus.COMPLETED,
            completed_at=datetime.now(UTC) - timedelta(hours=100),
        )
        store.create("fresh")
        store.update("fresh", status=JobStatus.COMPLETED, completed_at=datetime.now(UTC))
        removed = store.expire_old(ttl_hours=24.0)
        assert removed == 1
        assert store.get("old") is None
        assert store.get("fresh") is not None

    def test_pending_jobs_not_expired(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.create("pending")  # no completed_at
        assert store.expire_old(ttl_hours=0.0) == 0
        assert store.get("pending") is not None
