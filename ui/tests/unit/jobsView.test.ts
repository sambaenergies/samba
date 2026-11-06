import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { flushPromises, mount } from "@vue/test-utils";

import JobsView from "@/views/JobsView.vue";

const listJobsMock = vi.fn();

vi.mock("@/api/jobs", () => ({
  listJobs: (...args: unknown[]) => listJobsMock(...args),
  submitJob: vi.fn(),
  deleteJob: vi.fn(),
}));

vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));

describe("JobsView", () => {
  let pinia: ReturnType<typeof createPinia>;

  beforeEach(() => {
    vi.clearAllMocks();
    pinia = createPinia();
    setActivePinia(pinia);
  });

  function mountView() {
    return mount(JobsView, { global: { plugins: [pinia], stubs: { RouterLink: true } } });
  }

  it("says there are no runs only when the backend said so", async () => {
    listJobsMock.mockResolvedValue([]);
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("No runs yet");
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });

  it("shows the load error instead of an empty-history message when the backend is unreachable", async () => {
    listJobsMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.find('[role="alert"]').text()).toBe("Could not load jobs: Failed to fetch");
    expect(wrapper.text()).not.toContain("No runs yet");
  });
});
