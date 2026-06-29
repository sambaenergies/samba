import { apiClient, unwrap } from "@/api/http";
import type { ValidationResponse } from "@/api/types";

export async function validateScenario(scenario: unknown): Promise<ValidationResponse> {
  return unwrap(
    await apiClient.POST("/api/v1/validate", {
      body: { scenario: scenario as { [key: string]: unknown } },
    }),
  );
}
