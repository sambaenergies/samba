<script setup lang="ts">
import { onMounted } from "vue";
import { useConnectionStore } from "@/stores/connection";
import { useJobsStore } from "@/stores/jobs";
import NavSidebar from "@/components/layout/NavSidebar.vue";
import ConnectionBadge from "@/components/layout/ConnectionBadge.vue";

const connection = useConnectionStore();
const jobs = useJobsStore();

onMounted(() => {
  connection.startPolling();
  void jobs.refresh();
});
</script>

<template>
  <div class="flex min-h-screen">
    <NavSidebar />
    <div class="flex min-w-0 flex-1 flex-col">
      <header class="sticky top-0 z-10 flex items-center justify-end border-b border-slate-200 bg-white px-6 py-3">
        <ConnectionBadge />
      </header>
      <main class="min-w-0 flex-1 p-6">
        <RouterView />
      </main>
    </div>
  </div>
</template>
