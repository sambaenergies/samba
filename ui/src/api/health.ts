import { apiClient } from "@/api/http";
import type { HealthResponse } from "@/api/types";

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.GET("/health", {});
  return data as HealthResponse;
}
