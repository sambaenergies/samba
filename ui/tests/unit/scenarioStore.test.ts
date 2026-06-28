import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useScenarioStore } from "@/stores/scenario";

vi.mock("@/api/validate", () => ({
  validateScenario: vi.fn(async () => ({ valid: true, errors: [] })),
}));

describe("scenario store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("setField deep sets nested values", () => {
    const store = useScenarioStore();
    store.setField(["project", "name"], "Demo");
    expect(store.draft.project.name).toBe("Demo");
    expect(store.isDirty).toBe(true);
  });

  it("imports valid YAML", async () => {
    const store = useScenarioStore();
    await store.importYaml("schema_version: '1.0'\nproject:\n  name: Imported\n");
    expect(store.draft.project.name).toBe("Imported");
  });

  it("handles malformed YAML without throw", async () => {
    const store = useScenarioStore();
    await store.importYaml("project: [");
    expect(store.validationErrors.length).toBeGreaterThan(0);
  });

  it("exportYaml round trips through importYaml", async () => {
    const store = useScenarioStore();
    store.draft.project.name = "RoundTrip";
    const yaml = store.exportYaml();

    const store2 = useScenarioStore();
    await store2.importYaml(yaml);
    expect(store2.draft.project.name).toBe("RoundTrip");
  });
});
