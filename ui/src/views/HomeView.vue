<script setup lang="ts">
import { useConnectionStore } from "@/stores/connection";
import { useJobsStore } from "@/stores/jobs";

const connection = useConnectionStore();
const jobs = useJobsStore();
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-semibold">Home</h1>

    <section class="card">
      <h2 class="mb-2 text-lg font-medium">Connection</h2>
      <p class="text-sm text-slate-600">Backend: {{ connection.backendUrl }}</p>
      <p class="text-sm">Status: <strong class="capitalize">{{ connection.status }}</strong></p>
      <p v-if="connection.version" class="text-sm">Version: {{ connection.version }}</p>
      <p v-if="connection.solver" class="text-sm">Solver: {{ connection.solver }}</p>
      <button class="btn mt-3" @click="connection.checkConnection">Connect</button>
    </section>

    <section class="card">
      <h2 class="mb-2 text-lg font-medium">Recent Jobs</h2>
      <ul v-if="jobs.recent.length" class="space-y-2">
        <li v-for="job in jobs.recent" :key="job.run_id" class="text-sm">
          <RouterLink :to="`/results/${job.run_id}`" class="text-blue-600 hover:underline">
            {{ job.run_id }}
          </RouterLink>
          — {{ job.status }}
        </li>
      </ul>
      <p v-else class="text-sm text-slate-500">No jobs yet.</p>
      <div class="mt-4 flex gap-2">
        <RouterLink class="btn" to="/editor">New Scenario</RouterLink>
        <RouterLink class="btn" to="/jobs">View Jobs</RouterLink>
      </div>
    </section>
  </div>
</template>
