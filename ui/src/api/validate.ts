import { apiClient } from "@/api/http";
import type { ValidationResponse } from "@/api/types";

export async function validateScenario(scenario: unknown): Promise<ValidationResponse> {
  const { data } = await apiClient.POST("/api/v1/validate", {
    body: { scenario: scenario as { [key: string]: unknown } },
  });
  return data as ValidationResponse;
}
