# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
# If a copy of the MPL was not distributed with this file, You can obtain one at
# https://mozilla.org/MPL/2.0/.
"""samba_service.jobs -- In-process job store and background runner.

Architecture
------------
Solve jobs are executed in a :class:'concurrent.futures.ThreadPoolExecutor'.
HiGHS/CBC releases the GIL during its solve loop, so multiple jobs can make
real progress concurrently despite Python's GIL.

Each job is identified by a UUID4 *run_id* and passes through four states::

    PENDING -> RUNNING -> COMPLETED
                      -> FAILED

The ''JobStore'' is an in-process ''dict'' protected by a :class:'threading.Lock'.
All mutations are serialised through the lock.  Reads are done under the lock
as well to avoid torn reads of mutable ''Job'' objects.

Lifecycle
---------
1. Caller generates a ''run_id = str(uuid.uuid4())''.
2. :func:'submit_job' creates a ''PENDING'' job record and enqueues
   ''_run_job'' in the executor.
3. ''_run_job'' writes a temporary scenario YAML, calls ''samba.run()'',
   and updates the job to ''COMPLETED'' (or ''FAILED'').
4. Callers poll the store via :meth:'JobStore.get'.
5. Stale jobs are evicted by :meth:'JobStore.expire_old' (called lazily
   on each ''list_all'' call).

Thread safety
-------------
''JobStore'' is fully thread-safe.  ''submit_job'' and ''shutdown_executor''
must be called from the service's main thread (e.g. FastAPI lifespan hooks).

Persistence limitation
----------------------
The store is **in-process and non-persistent**: all job records (and any
in-flight solves) are lost when the service process restarts.  A client that
submitted a job and polls its ''run_id'' after a restart (k8s pod eviction,
OOM, redeploy) will receive a 404.  This is acceptable for development and
single-machine use; a deployment with auto-restart needs a persistent job
store (see audit item M2 / a future ''PersistentJobStore'').
"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

__all__ = [
    "JobStatus",
    "Job",
    "JobStore",
    "store",
    "init_executor",
    "shutdown_executor",
    "submit_job",
]


class JobStatus(StrEnum):
    """Life-cycle state of a background solve job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    """Metadata record for a single background optimisation job.

    Attributes
    ----------
    run_id:
        UUID4 string uniquely identifying this job.
    status:
        Current :class:'JobStatus'.
    submitted_at:
        UTC datetime when the job was submitted.
    started_at:
        UTC datetime when the worker thread picked up the job, or ''None''
        if still pending.
    completed_at:
        UTC datetime when the job finished (success or failure), or ''None''
        if still in progress.
    run_dir:
        Path to the artifact directory written by :func:'samba.run', or
        ''None'' until the job completes successfully.
    error:
        Human-readable error description if the job failed, else ''None''.
    kpis:
        KPI dict returned by :attr:'~samba.run_result.reader.RunResult.kpis',
        or ''None'' until the job completes successfully.
    sizing:
        List of sizing records (''{component, capacity, unit, count,
        capital_cost}''), or ''None'' until the job completes successfully.
    """

    run_id: str
    status: JobStatus = JobStatus.PENDING
    submitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    run_dir: Path | None = None
    error: str | None = None
    kpis: dict[str, Any] | None = None
    sizing: list[dict[str, Any]] | None = None
    solve_time_s: float | None = None


class JobStore:
    """Thread-safe, in-process job registry.

    All public methods acquire ''_lock'' for their entire duration.  The store
    maps *run_id* strings to :class:'Job' dataclass instances.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock: threading.Lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, run_id: str) -> Job:
        """Create a new ''PENDING'' job and add it to the store.

        Parameters
        ----------
        run_id:
            UUID4 identifier for the job.

        Returns
        -------
        Job
            The newly created job record.
        """
        job = Job(run_id=run_id)
        with self._lock:
            self._jobs[run_id] = job
        return job

    def get(self, run_id: str) -> Job | None:
        """Return the :class:'Job' for *run_id*, or ''None'' if not found.

        Returns a *copy* of the internal record so callers see a stable
        snapshot even if the worker thread is simultaneously updating it.
        """
        with self._lock:
            job = self._jobs.get(run_id)
            if job is None:
                return None
            # Shallow copy is sufficient -- all mutable fields are primitives
            # or immutable (Path, dict assigned atomically by the worker).
            import copy

            return copy.copy(job)

    def update(self, run_id: str, **kwargs: Any) -> None:
        """Set *kwargs* on the job identified by *run_id*.

        Silently ignores unknown *run_id* (job may have been expired).
        """
        with self._lock:
            job = self._jobs.get(run_id)
            if job is None:
                return
            for k, v in kwargs.items():
                setattr(job, k, v)

    def remove(self, run_id: str) -> bool:
        """Remove a job from the store.

        Returns
        -------
        bool
            ''True'' if the job existed and was removed, ''False'' otherwise.
        """
        with self._lock:
            return self._jobs.pop(run_id, None) is not None

    def list_all(self, status_filter: str | None = None) -> list[Job]:
        """Return a snapshot list of all jobs, sorted by ''submitted_at'' descending.

        Parameters
        ----------
        status_filter:
            Optional :class:'JobStatus' value string.  When provided, only
            jobs with a matching status are returned.
        """
        self.expire_old()  # lazily evict stale records
        with self._lock:
            jobs = list(self._jobs.values())
        if status_filter is not None:
            jobs = [j for j in jobs if j.status.value == status_filter]
        jobs.sort(key=lambda j: j.submitted_at, reverse=True)
        return jobs

    def expire_old(self, ttl_hours: float | None = None) -> int:
        """Evict completed/failed jobs older than *ttl_hours*.

        Parameters
        ----------
        ttl_hours:
            TTL in hours.  Defaults to
            ''config.job_ttl_hours'' when ''None''.

        Returns
        -------
        int
            Number of jobs removed.
        """
        from samba_service.config import config

        ttl = ttl_hours if ttl_hours is not None else config.job_ttl_hours
        cutoff_dt = datetime.now(UTC)
        evict_ids: list[str] = []
        with self._lock:
            for run_id, job in self._jobs.items():
                if job.status not in (JobStatus.COMPLETED, JobStatus.FAILED):
                    continue
                if job.completed_at is None:
                    continue
                age_hours = (cutoff_dt - job.completed_at).total_seconds() / 3600.0
                if age_hours > ttl:
                    evict_ids.append(run_id)
            for rid in evict_ids:
                del self._jobs[rid]
        if evict_ids:
            log.debug("Expired %d stale job(s) from the store.", len(evict_ids))
        return len(evict_ids)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------


def _make_store() -> JobStore:
    """Build the job store: SQLite-backed when ``config.persist_jobs`` else in-memory."""
    from samba_service.config import config

    if config.persist_jobs:
        from samba_service.persistent_jobs import PersistentJobStore

        return PersistentJobStore(config.run_base_dir / "jobs.db")
    return JobStore()


#: Global job store -- imported by ''app.py'' and any code that needs to read
#: job state.  In-memory by default; SQLite-backed when SAMBA_PERSIST_JOBS is set.
store: JobStore = _make_store()

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def init_executor(max_workers: int = 4) -> None:
    """Initialise the background ''ThreadPoolExecutor''.

    Should be called once from the FastAPI *lifespan* startup hook.
    Calling it again after a prior :func:'shutdown_executor' is safe.
    """
    global _executor  # noqa: PLW0603
    with _executor_lock:
        if _executor is not None:
            return  # already initialised -- idempotent
        _executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="samba-job",
        )
    log.info("Job executor initialised (max_workers=%d).", max_workers)


def shutdown_executor(wait: bool = False) -> None:
    """Shut down the background executor.

    Should be called from the FastAPI *lifespan* shutdown hook.

    Parameters
    ----------
    wait:
        If ''True'', block until all running jobs finish.  If ''False''
        (default), cancel pending futures and do not wait for active jobs.
    """
    global _executor  # noqa: PLW0603
    with _executor_lock:
        if _executor is None:
            return
        _executor.shutdown(wait=wait, cancel_futures=not wait)
        _executor = None
    log.info("Job executor shut down.")


# ---------------------------------------------------------------------------
# Job submission
# ---------------------------------------------------------------------------


def submit_job(
    run_id: str,
    scenario_dict: dict[str, Any],
    run_dir_name: str | None = None,
) -> Future[None]:
    """Create a job record and submit it to the background executor.

    Parameters
    ----------
    run_id:
        UUID4 identifier (caller is responsible for generating this with
        ''uuid.uuid4()'').
    scenario_dict:
        Raw scenario dict as received from the API request body.
    run_dir_name:
        Optional directory name stem under ''config.run_base_dir''.  When
        ''None'' the service uses a timestamped subdirectory.

    Returns
    -------
    concurrent.futures.Future
        The submitted future.  Callers generally don't need to hold onto it;
        job state is tracked via the :data:'store'.

    Raises
    ------
    RuntimeError
        When :func:'init_executor' has not been called yet.
    """
    global _executor  # noqa: PLW0603
    with _executor_lock:
        if _executor is None:
            raise RuntimeError(
                "Job executor is not initialised. Call samba_service.jobs.init_executor() first."
            )
        store.create(run_id)
        future = _executor.submit(_run_job, run_id, scenario_dict, run_dir_name)
    log.info("Submitted job %s to executor.", run_id)
    return future


# ---------------------------------------------------------------------------
# Worker function (runs in a background thread)
# ---------------------------------------------------------------------------


def _run_job(
    run_id: str,
    scenario_dict: dict[str, Any],
    run_dir_name: str | None,
) -> None:
    """Execute the SAMBA pipeline for *run_id*.

    This function runs entirely in a background thread spawned by the
    executor.  All state updates go through :data:'store'.

    Steps
    -----
    1. Mark job ''RUNNING''.
    2. Write scenario dict to a temporary YAML file under
       ''{config.run_base_dir}/.tmp/{run_id}.yaml''.
    3. Call ''samba.run()'', passing the temp YAML path.
    4. On success: mark ''COMPLETED'', persist ''kpis'' and ''sizing''.
    5. On failure: mark ''FAILED'', persist ''error''.
    6. Delete the temporary YAML file (in a ''finally'' block).
    """

    import yaml

    import samba
    from samba.scenario import load_scenario
    from samba_service.config import config

    store.update(
        run_id,
        status=JobStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    log.info("Job %s started.", run_id)

    tmp_yaml: Path | None = None
    try:
        # -- Write temp YAML ---------------------------------------------------
        tmp_dir = config.run_base_dir / ".tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_yaml = tmp_dir / f"{run_id}.yaml"
        tmp_yaml.write_text(yaml.dump(scenario_dict, allow_unicode=True), encoding="utf-8")

        # -- Resolve arrays ----------------------------------------------------
        scene = load_scenario(tmp_yaml)
        from samba.input_resolver import resolve_arrays

        load_kw, pv_per_kwp, wind_power_kw = resolve_arrays(scene, config.data_dir)

        # -- Build SolverConfig ------------------------------------------------
        from samba.solver.runner import SolverConfig

        solver_cfg = SolverConfig(
            solver_name=config.solver,
            time_limit_s=config.time_limit_s,
        )

        # -- Run SAMBA ---------------------------------------------------------
        output_dir = config.run_base_dir / run_dir_name if run_dir_name else config.run_base_dir
        result = samba.run(
            scene,
            load_kw=load_kw,
            pv_per_kwp=pv_per_kwp,
            wind_power_kw=wind_power_kw,
            output_dir=output_dir,
            config=solver_cfg,
            # Resolve weather + thermal/HP CSV paths relative to the data dir so
            # degree-day thermal demand is computed (not stubbed to zero).
            scenario_dir=config.data_dir,
        )

        # -- Extract sizing ----------------------------------------------------
        sizing_records: list[dict[str, Any]] | None = None
        if result.sizing is not None and not result.sizing.empty:
            sizing_records = result.sizing.to_dict(orient="records")

        # -- Mark COMPLETED ----------------------------------------------------
        store.update(
            run_id,
            status=JobStatus.COMPLETED,
            completed_at=datetime.now(UTC),
            run_dir=result.run_dir,
            kpis=result.kpis,
            sizing=sizing_records,
            solve_time_s=result.metadata.get("wall_time_seconds"),
        )
        log.info("Job %s completed successfully (run_dir=%s).", run_id, result.run_dir)

    except Exception as exc:  # noqa: BLE001
        log.exception("Job %s failed: %s", run_id, exc)
        store.update(
            run_id,
            status=JobStatus.FAILED,
            completed_at=datetime.now(UTC),
            error=str(exc),
        )
    finally:
        if tmp_yaml is not None and tmp_yaml.exists():
            import contextlib

            with contextlib.suppress(OSError):
                tmp_yaml.unlink()


def generate_run_id() -> str:
    """Return a new UUID4 run identifier."""
    return str(uuid.uuid4())
