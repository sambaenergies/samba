<script setup lang="ts">
import { computed } from "vue";
import { useConnectionStore } from "@/stores/connection";

const connection = useConnectionStore();

const dotClass = computed(() => {
  if (connection.status === "connected") return "bg-emerald-500";
  if (connection.status === "checking") return "bg-amber-500";
  if (connection.status === "incompatible") return "bg-orange-500";
  return "bg-red-500";
});
</script>

<template>
  <div class="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 text-xs">
    <span class="h-2 w-2 rounded-full" :class="dotClass" />
    <span class="capitalize">{{ connection.status }}</span>
    <span v-if="connection.version" class="text-slate-500">v{{ connection.version }}</span>
  </div>
</template>
