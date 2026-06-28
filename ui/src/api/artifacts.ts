import { apiFetch } from "@/api/client";
import { useConnectionStore } from "@/stores/connection";

export function getArtifactUrl(runId: string, filename: string): string {
  const store = useConnectionStore();
  return `${store.backendUrl.replace(/\/$/, "")}/api/v1/jobs/${runId}/artifacts/${filename}`;
}

export async function fetchArtifact(runId: string, filename: string): Promise<Blob> {
  const response = await apiFetch(`/api/v1/jobs/${runId}/artifacts/${filename}`);
  return response.blob();
}
