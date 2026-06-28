import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";

import TariffForm from "@/components/scenario/TariffForm.vue";
import { useScenarioStore } from "@/stores/scenario";

describe("TariffForm", () => {
  let pinia: ReturnType<typeof createPinia>;

  beforeEach(() => {
    pinia = createPinia();
    setActivePinia(pinia);
  });

  it("enabling the sell toggle creates a sell tariff", async () => {
    const store = useScenarioStore();
    expect(store.draft.tariff.sell ?? null).toBeNull();

    const wrapper = mount(TariffForm, {
      global: { plugins: [pinia] },
    });

    // First checkbox is the "Sell / feed-in tariff" toggle.
    const sellToggle = wrapper.find('input[type="checkbox"]');
    await sellToggle.setValue(true);

    expect(store.draft.tariff.sell).not.toBeNull();
    expect(store.draft.tariff.sell?.type).toBe("flat");
  });
});
