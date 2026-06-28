<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, MarkLineComponent, TooltipComponent } from "echarts/components";

import type { CashflowRow } from "@/api/types";

use([CanvasRenderer, LineChart, GridComponent, MarkLineComponent, TooltipComponent]);

const props = defineProps<{
  rows: CashflowRow[] | null;
}>();

const option = computed(() => {
  const rows = props.rows ?? [];
  return {
    animation: false,
    tooltip: { trigger: "axis" },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: "category", data: rows.map((row) => row.year) },
    yAxis: { type: "value", name: "NPV" },
    series: [
      {
        type: "line",
        smooth: true,
        showSymbol: false,
        data: rows.map((row) => row.cumulative_npv),
        markLine: { data: [{ yAxis: 0 }] },
      },
    ],
  };
});
</script>

<template>
  <div class="card">
    <h3 class="mb-2 text-lg font-semibold">Cumulative NPV</h3>
    <VChart :option="option" autoresize style="height: 300px" />
  </div>
</template>
