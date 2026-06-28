import { defineStore } from "pinia";

import type { JobRecord } from "@/api/types";
import { deleteJob, listJobs, submitJob } from "@/api/jobs";
import { useScenarioStore } from "@/stores/scenario";

export const useJobsStore = defineStore("jobs", {
  state: () => ({
    list: [] as JobRecord[],
  }),
  getters: {
    recent(state): JobRecord[] {
      return state.list.slice(0, 5);
    },
    pendingCount(state): number {
      return state.list.filter((job) => job.status === "pending" || job.status === "running").length;
    },
  },
  actions: {
    async submitCurrent() {
      const scenarioStore = useScenarioStore();
      const payload = scenarioStore.draft;
      const result = await submitJob(payload);
      await this.refresh();
      return result.run_id;
    },
    async refresh() {
      this.list = await listJobs();
    },
    async remove(runId: string) {
      await deleteJob(runId);
      this.list = this.list.filter((job) => job.run_id !== runId);
    },
  },
});
