// Route-aware HTTP client generated from the published OpenAPI contract.
//
// openapi-fetch builds an absolute Request from (baseUrl + path). Since the backend
// URL is user-configurable, baseUrl is a sentinel and a custom `fetch` adapts the
// Request back to `apiFetch(path, init)` -- which owns the dynamic backendUrl, the
// X-API-Key injection, and the ApiError throw-on-non-2xx contract. So the typed
// client and the hand-written artifacts client share exactly one transport, and
// call sites keep consuming failures via try/catch (never openapi-fetch's
// `{ data, error }` tuple). Because apiFetch throws on !ok, a returned `data` is
// present for any body-returning endpoint.

import createClient from "openapi-fetch";

import { ApiError, apiFetch } from "@/api/client";
import type { paths } from "@/api/generated/openapi";

const SENTINEL_BASE = "http://contract.invalid";

async function contractFetch(input: Request): Promise<Response> {
  const { pathname, search } = new URL(input.url);
  const hasBody = input.method !== "GET" && input.method !== "DELETE";
  return apiFetch(`${pathname}${search}`, {
    method: input.method,
    headers: input.headers,
    body: hasBody ? await input.text() : undefined,
  });
}

export const apiClient = createClient<paths>({
  baseUrl: SENTINEL_BASE,
  fetch: contractFetch as typeof fetch,
});

/** Unwrap an openapi-fetch result to its typed body without an `as` cast.
 *  `contractFetch` throws on non-2xx, so `data` is present for any body-returning
 *  endpoint; the guard only defends against an unexpected empty 2xx body. */
export function unwrap<T>(result: { data?: T; response: Response }): T {
  if (result.data === undefined) {
    throw new ApiError(result.response.status, "empty response body");
  }
  return result.data;
}
