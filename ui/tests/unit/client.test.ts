import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { apiGet, ApiError } from "@/api/client";
import { useConnectionStore } from "@/stores/connection";

describe("api client", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("sets X-API-Key when present", async () => {
    const store = useConnectionStore();
    store.setApiKey("secret");

    const mockFetch = vi.fn(async (_url: string, init?: RequestInit) => {
      const headers = init?.headers as Headers;
      expect(headers.get("X-API-Key")).toBe("secret");
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });

    vi.stubGlobal("fetch", mockFetch);
    const result = await apiGet<{ ok: boolean }>("/health");
    expect(result.ok).toBe(true);
  });

  it("throws ApiError on non-2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "bad" }), {
          status: 400,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(apiGet("/health")).rejects.toBeInstanceOf(ApiError);
  });
});
