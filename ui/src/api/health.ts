import { apiClient, unwrap } from "@/api/http";
import type { HealthResponse } from "@/api/types";

export async function fetchHealth(): Promise<HealthResponse> {
  return unwrap(await apiClient.GET("/health", {}));
}
