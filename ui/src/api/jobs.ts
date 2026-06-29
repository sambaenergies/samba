import { apiClient } from "@/api/http";
import type { JobRecord, JobSubmitResponse } from "@/api/types";

// The contract's request `scenario` is a permissive mapping (validated server side,
// so a bad scenario returns a structured 200/422 body rather than a request-shape
// rejection). Accept any value and pass it through.
type ScenarioMapping = { [key: string]: unknown };

export async function submitJob(scenario: unknown): Promise<JobSubmitResponse> {
  const { data } = await apiClient.POST("/api/v1/jobs", {
    body: { scenario: scenario as ScenarioMapping },
  });
  return data as JobSubmitResponse;
}

export async function getJob(runId: string): Promise<JobRecord> {
  const { data } = await apiClient.GET("/api/v1/jobs/{run_id}", {
    params: { path: { run_id: runId } },
  });
  return data as JobRecord;
}

export async function listJobs(): Promise<JobRecord[]> {
  const { data } = await apiClient.GET("/api/v1/jobs", {});
  return data as JobRecord[];
}

export async function deleteJob(runId: string): Promise<void> {
  await apiClient.DELETE("/api/v1/jobs/{run_id}", {
    params: { path: { run_id: runId } },
  });
}
