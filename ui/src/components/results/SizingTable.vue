<script setup lang="ts">
import { computed } from "vue";

import type { SizingRow } from "@/api/types";

const props = defineProps<{
  rows: SizingRow[] | null;
  npcTotal?: number | null;
}>();

const filtered = computed(() => (props.rows ?? []).filter((row) => row.capacity > 0));
</script>

<template>
  <div class="card overflow-x-auto">
    <h3 class="mb-2 text-lg font-semibold">Sizing Summary</h3>
    <table class="min-w-full text-sm">
      <thead>
        <tr class="border-b border-slate-200 text-left">
          <th class="px-2 py-2">Component</th>
          <th class="px-2 py-2">Capacity</th>
          <th class="px-2 py-2">Unit</th>
          <th class="px-2 py-2">Capex</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in filtered" :key="row.component" class="border-b border-slate-100">
          <td class="px-2 py-2">{{ row.component }}</td>
          <td class="px-2 py-2">{{ row.capacity.toLocaleString() }}</td>
          <td class="px-2 py-2">{{ row.unit }}</td>
          <td class="px-2 py-2">{{ row.capital_cost.toLocaleString() }}</td>
        </tr>
        <tr v-if="npcTotal !== null && npcTotal !== undefined" class="border-t border-slate-200 font-semibold">
          <td class="px-2 py-2" colspan="3">Total NPC</td>
          <td class="px-2 py-2">{{ npcTotal.toLocaleString() }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
