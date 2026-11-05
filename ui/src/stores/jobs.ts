import { defineStore } from "pinia";

import type { JobRecord } from "@/api/types";
import { deleteJob, listJobs, submitJob } from "@/api/jobs";
import { useScenarioStore } from "@/stores/scenario";

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

// Like the connection store, these actions never reject: a failed request
// becomes `error`, which the views render, and `list` keeps the last rows the
// backend actually returned. Callers fire `refresh()` without awaiting it
// (AppShell on every mount, before the sidecar is up), so a rejection would
// otherwise go unhandled and the user would see nothing.
export const useJobsStore = defineStore("jobs", {
  state: () => ({
    list: [] as JobRecord[],
    error: null as string | null,
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
    /** Submit the scenario draft. Returns the new run id, or null when the submit failed. */
    async submitCurrent(): Promise<string | null> {
      const scenarioStore = useScenarioStore();
      let runId: string;
      try {
        runId = (await submitJob(scenarioStore.draft)).run_id;
      } catch (error) {
        this.error = `Could not submit the run: ${messageOf(error)}`;
        return null;
      }
      this.error = null;
      // The run exists server side even if this refresh fails, so the id is
      // still returned; refresh() reports its own failure.
      await this.refresh();
      return runId;
    },
    async refresh() {
      try {
        this.list = await listJobs();
        this.error = null;
      } catch (error) {
        this.error = `Could not load jobs: ${messageOf(error)}`;
      }
    },
    async remove(runId: string) {
      try {
        await deleteJob(runId);
      } catch (error) {
        this.error = `Could not delete run ${runId}: ${messageOf(error)}`;
        return;
      }
      this.error = null;
      this.list = this.list.filter((job) => job.run_id !== runId);
    },
  },
});
