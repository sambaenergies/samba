import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { fetchHealth } from "@/api/health";

describe("fetchHealth", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("maps health response", async () => {
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

    const result = await fetchHealth();
    expect(result.status).toBe("ok");
    expect(result.version).toBe("3.0.0");
  });
});
