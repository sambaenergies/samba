import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";

import ComponentCard from "@/components/scenario/ComponentCard.vue";
import { useScenarioStore } from "@/stores/scenario";

describe("ComponentCard", () => {
  let pinia: ReturnType<typeof createPinia>;

  beforeEach(() => {
    pinia = createPinia();
    setActivePinia(pinia);
  });

  it("toggles enabled state", async () => {
    const store = useScenarioStore();
    store.draft.components.pv!.enabled = true;

    const wrapper = mount(ComponentCard, {
      props: { name: "pv" },
      global: {
        plugins: [pinia],
      },
    });

    const toggle = wrapper.find('input[type="checkbox"]');
    await toggle.setValue(false);
    expect(store.draft.components.pv!.enabled).toBe(false);
  });

  it("renders schema fields for the component", () => {
    const store = useScenarioStore();
    store.draft.components.pv!.enabled = true;

    const wrapper = mount(ComponentCard, {
      props: { name: "pv" },
      global: { plugins: [pinia] },
    });

    // PV exposes a module_type select with the real enum options.
    const options = wrapper.findAll("option").map((o) => o.text());
    expect(options).toContain("monofacial");
    expect(options).toContain("bifacial");
  });
});
