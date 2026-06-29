import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useConnectionStore } from "@/stores/connection";

describe("connection store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  function stubHealth(apiVersion: string): void {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            status: "ok",
            version: "5.3.1",
            api_version: apiVersion,
            contract_version: "1.0",
            capabilities: ["async_jobs"],
            solver: "appsi_highs",
            solver_ready: true,
            active_jobs: 0,
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );
  }

  it("sets connected on a compatible API major", async () => {
    stubHealth("1.0.0"); // matches the vendored contract's api_version major
    const store = useConnectionStore();
    await store.checkConnection();
    expect(store.status).toBe("connected");
    expect(store.apiVersion).toBe("1.0.0");
  });

  it("sets incompatible on an API major mismatch", async () => {
    stubHealth("2.0.0"); // backend reachable but speaks a newer API major
    const store = useConnectionStore();
    await store.checkConnection();
    expect(store.status).toBe("incompatible");
  });

  it("sets unreachable on failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("err", { status: 503 })));

    const store = useConnectionStore();
    await store.checkConnection();
    expect(store.status).toBe("unreachable");
  });
});
