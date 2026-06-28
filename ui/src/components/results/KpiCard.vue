<script setup lang="ts">
defineProps<{
  label: string;
  value: number | null;
  unit?: string;
}>();
</script>

<template>
  <div class="rounded-lg border border-slate-200 bg-white p-3">
    <p class="text-xs uppercase tracking-wide text-slate-500">{{ label }}</p>
    <p class="mt-1 text-2xl font-semibold">
      <span v-if="value !== null">{{ value.toLocaleString(undefined, { maximumFractionDigits: 3 }) }}</span>
      <span v-else>—</span>
      <span v-if="unit" class="ml-1 text-sm text-slate-500">{{ unit }}</span>
    </p>
  </div>
</template>
