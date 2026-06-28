<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { useIntervalFn } from "@vueuse/core";

import { useJobsStore } from "@/stores/jobs";

const jobs = useJobsStore();
const router = useRouter();

const sortedJobs = computed(() =>
  [...jobs.list].sort((left, right) => right.submitted_at.localeCompare(left.submitted_at)),
);

const { pause, resume } = useIntervalFn(() => {
  void jobs.refresh();
}, 5_000, { immediate: false });

function statusClass(status: string): string {
  if (status === "pending") return "bg-blue-100 text-blue-700";
  if (status === "running") return "bg-amber-100 text-amber-700";
  if (status === "completed") return "bg-emerald-100 text-emerald-700";
  return "bg-red-100 text-red-700";
}

async function goResults(runId: string) {
  await router.push(`/results/${runId}`);
}

onMounted(async () => {
  await jobs.refresh();
});

watch(
  () => jobs.pendingCount,
  (count) => {
    if (count > 0) {
      resume();
      return;
    }
    pause();
  },
  { immediate: true },
);
</script>

<template>
  <div class="space-y-4">
    <header class="card flex items-center justify-between">
      <h1 class="text-2xl font-semibold">Jobs</h1>
      <RouterLink class="btn" to="/editor">Submit New Scenario</RouterLink>
    </header>

    <section class="card overflow-x-auto">
      <table class="min-w-full text-sm">
        <thead>
          <tr class="border-b border-slate-200 text-left">
            <th class="px-2 py-2">Run ID</th>
            <th class="px-2 py-2">Created</th>
            <th class="px-2 py-2">Status</th>
            <th class="px-2 py-2">Progress</th>
            <th class="px-2 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in sortedJobs" :key="job.run_id" class="border-b border-slate-100 align-top">
            <td class="px-2 py-2 font-mono text-xs">{{ job.run_id.slice(0, 12) }}</td>
            <td class="px-2 py-2">{{ new Date(job.submitted_at).toLocaleString() }}</td>
            <td class="px-2 py-2">
              <span class="rounded px-2 py-1 text-xs" :class="statusClass(job.status)">
                {{ job.status }}
              </span>
            </td>
            <td class="px-2 py-2">
              <div class="h-2 w-40 rounded bg-slate-200">
                <div
                  class="h-2 rounded"
                  :class="job.status === 'failed' ? 'bg-red-400' : 'bg-slate-700'"
                  :style="{
                    width: `${
                      job.status === 'completed' || job.status === 'failed'
                        ? 100
                        : job.status === 'running'
                          ? 66
                          : 10
                    }%`,
                  }"
                />
              </div>
            </td>
            <td class="px-2 py-2">
              <div class="flex gap-2">
                <button class="btn" :disabled="job.status !== 'completed'" @click="goResults(job.run_id)">
                  View Results
                </button>
                <button class="btn" @click="jobs.remove(job.run_id)">Delete</button>
              </div>
              <p v-if="job.error" class="mt-2 text-xs text-red-600">{{ job.error }}</p>
            </td>
          </tr>
          <tr v-if="!sortedJobs.length">
            <td colspan="5" class="px-2 py-6 text-center text-slate-500">No runs yet. Start by creating a scenario.</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>
