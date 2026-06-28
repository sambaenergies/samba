<script setup lang="ts">
import type { CashflowRow } from "@/api/types";

defineProps<{
  rows: CashflowRow[] | null;
}>();

const columns: Array<keyof CashflowRow> = [
  "year",
  "investment",
  "om",
  "fuel",
  "grid_net",
  "replacement",
  "salvage",
  "total",
  "cumulative_npv",
];

function fmt(column: keyof CashflowRow, value: number): string {
  if (column === "year") {
    return String(value);
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
</script>

<template>
  <div class="overflow-x-auto rounded-lg border border-slate-200">
    <table class="min-w-full text-sm">
      <thead>
        <tr class="border-b border-slate-200 text-left">
          <th v-for="column in columns" :key="column" class="px-2 py-2">{{ column }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows ?? []" :key="row.year" class="border-b border-slate-100">
          <td v-for="column in columns" :key="`${row.year}-${column}`" class="px-2 py-2">
            {{ fmt(column, row[column]) }}
          </td>
        </tr>
        <tr v-if="!(rows?.length)">
          <td :colspan="columns.length" class="px-2 py-5 text-center text-slate-500">No economics rows.</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
