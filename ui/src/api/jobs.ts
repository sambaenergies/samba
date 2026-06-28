import { apiDelete, apiGet, apiPost } from "@/api/client";
import type { JobRecord } from "@/api/types";

export function submitJob(scenario: unknown): Promise<{ run_id: string }> {
  return apiPost<{ run_id: string }>("/api/v1/jobs", { scenario });
}

export function getJob(runId: string): Promise<JobRecord> {
  return apiGet<JobRecord>(`/api/v1/jobs/${runId}`);
}

export function listJobs(): Promise<JobRecord[]> {
  return apiGet<JobRecord[]>("/api/v1/jobs");
}

export function deleteJob(runId: string): Promise<void> {
  return apiDelete(`/api/v1/jobs/${runId}`);
}
