import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useConnectionStore } from "@/stores/connection";

describe("connection store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("sets connected on successful health", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            status: "ok",
            version: "3.0.0",
            solver: "appsi_highs",
            solver_ready: true,
            active_jobs: 0,
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );

    const store = useConnectionStore();
    await store.checkConnection();
    expect(store.status).toBe("connected");
  });

  it("sets unreachable on failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("err", { status: 503 })));

    const store = useConnectionStore();
    await store.checkConnection();
    expect(store.status).toBe("unreachable");
  });
});
