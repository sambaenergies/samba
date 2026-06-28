<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { PieChart } from "echarts/charts";
import { LegendComponent, TooltipComponent } from "echarts/components";

import type { CashflowRow } from "@/api/types";

use([CanvasRenderer, PieChart, LegendComponent, TooltipComponent]);

const props = defineProps<{
  rows: CashflowRow[] | null;
}>();

const option = computed(() => {
  const rows = props.rows ?? [];
  const total = rows.reduce(
    (acc, row) => {
      acc.capex += row.investment + row.replacement;
      acc.opex += row.om;
      acc.fuel += row.fuel;
      acc.grid += row.grid_net;
      return acc;
    },
    { capex: 0, opex: 0, fuel: 0, grid: 0 },
  );

  return {
    animation: false,
    tooltip: { trigger: "item" },
    legend: { bottom: 0 },
    series: [
      {
        type: "pie",
        radius: ["45%", "70%"],
        data: [
          { name: "Capex", value: total.capex },
          { name: "Opex", value: total.opex },
          { name: "Fuel", value: total.fuel },
          { name: "Grid Import", value: total.grid },
        ],
      },
    ],
  };
});
</script>

<template>
  <div class="card">
    <h3 class="mb-2 text-lg font-semibold">Lifecycle Cost Breakdown</h3>
    <VChart :option="option" autoresize style="height: 300px" />
  </div>
</template>
