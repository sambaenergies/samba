import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import type { JobRecord } from "@/api/types";
import { useJobsStore } from "@/stores/jobs";
import { useScenarioStore } from "@/stores/scenario";

const listJobsMock = vi.fn();
const submitJobMock = vi.fn();
const deleteJobMock = vi.fn();

vi.mock("@/api/jobs", () => ({
  listJobs: (...args: unknown[]) => listJobsMock(...args),
  submitJob: (...args: unknown[]) => submitJobMock(...args),
  deleteJob: (...args: unknown[]) => deleteJobMock(...args),
}));

function job(runId: string, status: JobRecord["status"]): JobRecord {
  return {
    run_id: runId,
    status,
    submitted_at: "2026-01-01T00:00:00Z",
    artifacts: [],
  };
}

describe("jobs store", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setActivePinia(createPinia());
  });

  it("refresh replaces the list with what the API returns", async () => {
    listJobsMock.mockResolvedValue([job("r1", "completed"), job("r2", "running")]);
    const store = useJobsStore();

    await store.refresh();

    expect(store.list.map((j) => j.run_id)).toEqual(["r1", "r2"]);
  });

  it("recent caps at five, preserving API order", async () => {
    listJobsMock.mockResolvedValue(
      ["r1", "r2", "r3", "r4", "r5", "r6", "r7"].map((id) => job(id, "completed")),
    );
    const store = useJobsStore();

    await store.refresh();

    expect(store.list).toHaveLength(7);
    expect(store.recent.map((j) => j.run_id)).toEqual(["r1", "r2", "r3", "r4", "r5"]);
  });

  it("pendingCount counts pending and running, and nothing else", async () => {
    listJobsMock.mockResolvedValue([
      job("a", "pending"),
      job("b", "running"),
      job("c", "completed"),
      job("d", "failed"),
    ]);
    const store = useJobsStore();

    await store.refresh();

    expect(store.pendingCount).toBe(2);
  });

  it("remove deletes server-side then drops the row locally", async () => {
    listJobsMock.mockResolvedValue([job("r1", "completed"), job("r2", "completed")]);
    deleteJobMock.mockResolvedValue(undefined);
    const store = useJobsStore();
    await store.refresh();

    await store.remove("r1");

    expect(deleteJobMock).toHaveBeenCalledWith("r1");
    expect(store.list.map((j) => j.run_id)).toEqual(["r2"]);
  });

  it("remove leaves the list alone and reports the error when the delete fails", async () => {
    listJobsMock.mockResolvedValue([job("r1", "completed")]);
    deleteJobMock.mockRejectedValue(new Error("boom"));
    const store = useJobsStore();
    await store.refresh();

    await expect(store.remove("r1")).resolves.toBeUndefined();
    expect(store.list.map((j) => j.run_id)).toEqual(["r1"]);
    expect(store.error).toBe("Could not delete run r1: boom");
  });

  it("submitCurrent submits the scenario draft, refreshes, and returns the run id", async () => {
    submitJobMock.mockResolvedValue({ run_id: "new-run" });
    listJobsMock.mockResolvedValue([job("new-run", "pending")]);
    const scenario = useScenarioStore();
    const store = useJobsStore();

    const runId = await store.submitCurrent();

    expect(submitJobMock).toHaveBeenCalledWith(scenario.draft);
    expect(runId).toBe("new-run");
    // refresh() is awaited inside submitCurrent, so the list is already current.
    expect(listJobsMock).toHaveBeenCalledTimes(1);
    expect(store.list.map((j) => j.run_id)).toEqual(["new-run"]);
  });

  it("submitCurrent reports the error and returns null when the submit fails", async () => {
    submitJobMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const store = useJobsStore();

    await expect(store.submitCurrent()).resolves.toBeNull();
    expect(listJobsMock).not.toHaveBeenCalled();
    expect(store.error).toBe("Could not submit the run: Failed to fetch");
  });

  it("submitCurrent still returns the run id when only the follow-up refresh fails", async () => {
    // The run exists server side; reporting the submit as failed would invite a
    // duplicate resubmission.
    submitJobMock.mockResolvedValue({ run_id: "new-run" });
    listJobsMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const store = useJobsStore();

    await expect(store.submitCurrent()).resolves.toBe("new-run");
    expect(store.error).toBe("Could not load jobs: Failed to fetch");
  });

  it("refresh does not reject when the API is unreachable: it keeps the list and reports the error", async () => {
    // AppShell.vue calls `void jobs.refresh()` on every mount, which is before
    // the sidecar is up on first launch. A rejection there is unhandled.
    listJobsMock.mockResolvedValue([job("r1", "completed")]);
    const store = useJobsStore();
    await store.refresh();
    expect(store.error).toBeNull();

    listJobsMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(store.refresh()).resolves.toBeUndefined();
    expect(store.list.map((j) => j.run_id)).toEqual(["r1"]);
    expect(store.error).toBe("Could not load jobs: Failed to fetch");
  });

  it("a successful refresh clears a previous error", async () => {
    listJobsMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const store = useJobsStore();
    await store.refresh();
    expect(store.error).not.toBeNull();

    listJobsMock.mockResolvedValue([job("r1", "completed")]);
    await store.refresh();

    expect(store.error).toBeNull();
    expect(store.list.map((j) => j.run_id)).toEqual(["r1"]);
  });
});
