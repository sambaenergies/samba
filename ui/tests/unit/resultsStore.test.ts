import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useResultsStore } from "@/stores/results";

const getJobMock = vi.fn();
const fetchArtifactMock = vi.fn();

vi.mock("@/api/jobs", () => ({
  getJob: (...args: unknown[]) => getJobMock(...args),
}));

vi.mock("@/api/artifacts", () => ({
  fetchArtifact: (...args: unknown[]) => fetchArtifactMock(...args),
}));

describe("results store", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setActivePinia(createPinia());
  });

  it("loads completed run and fetches artifacts", async () => {
    getJobMock.mockResolvedValue({
      run_id: "r1",
      status: "completed",
      submitted_at: "2026-01-01T00:00:00Z",
      started_at: null,
      completed_at: null,
      progress_pct: 100,
      error: null,
      artifacts: ["kpis.json", "dispatch.csv", "economics.json"],
    });

    fetchArtifactMock.mockImplementation(async (_runId: string, filename: string) => {
      if (filename === "kpis.json") {
        return new Blob([
          JSON.stringify({
            kpi_contract_version: "2.1",
            npc: 1000,
            lcoe: 0.1,
            lpsp: 0,
            renewable_fraction: 0.6,
            total_emissions_kg: 10,
          }),
        ]);
      }
      if (filename === "dispatch.csv") {
        return new Blob(["timestamp,pv_gen,eload\n2026-01-01 00:00,1,2\n"]);
      }
      return new Blob([JSON.stringify({ cashflow_annual: [] })]);
    });

    const store = useResultsStore();
    await store.loadResult("r1");

    expect(store.kpis?.npc).toBe(1000);
    expect(store.dispatch?.timestamps.length).toBe(1);
    expect(store.cashflows).toEqual([]);
  });

  it("stops polling on failed status", async () => {
    getJobMock.mockResolvedValue({
      run_id: "r2",
      status: "failed",
      submitted_at: "2026-01-01T00:00:00Z",
      started_at: null,
      completed_at: null,
      progress_pct: 20,
      error: "failed",
      artifacts: [],
    });

    const store = useResultsStore();
    await store.loadResult("r2");
    expect(store.pollingActive).toBe(false);
  });
});
