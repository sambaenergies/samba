import { apiPost } from "@/api/client";
import type { ValidationResponse } from "@/api/types";

export function validateScenario(scenario: unknown): Promise<ValidationResponse> {
  return apiPost<ValidationResponse>("/api/v1/validate", { scenario });
}
