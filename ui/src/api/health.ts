import { apiGet } from "@/api/client";
import type { HealthResponse } from "@/api/types";

export function fetchHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health");
}
