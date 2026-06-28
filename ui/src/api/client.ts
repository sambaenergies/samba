import { useConnectionStore } from "@/stores/connection";

export class ApiError extends Error {
  public readonly status: number;
  public readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(`API request failed with status ${status}`);
    this.status = status;
    this.body = body;
  }
}

function normalizePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

function baseUrlFromStore(): string {
  const store = useConnectionStore();
  return store.backendUrl.replace(/\/$/, "");
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const store = useConnectionStore();
  const headers = new Headers(init?.headers ?? {});
  if (store.apiKey) {
    headers.set("X-API-Key", store.apiKey);
  }

  const response = await fetch(`${baseUrlFromStore()}${normalizePath(path)}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    const body = contentType.includes("application/json")
      ? await response.json().catch(() => null)
      : await response.text().catch(() => null);
    throw new ApiError(response.status, body);
  }

  return response;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await apiFetch(path, { method: "GET" });
  return (await response.json()) as T;
}

export async function apiPost<T>(path: string, payload: unknown): Promise<T> {
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return (await response.json()) as T;
}

export async function apiDelete(path: string): Promise<void> {
  await apiFetch(path, { method: "DELETE" });
}
