<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { BarChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";

import type { MonthlyRow } from "@/api/types";

use([CanvasRenderer, BarChart, GridComponent, LegendComponent, TooltipComponent]);

const props = withDefaults(
  defineProps<{
    data: MonthlyRow[] | null;
    height?: string;
  }>(),
  {
    height: "340px",
  },
);

const option = computed(() => {
  const rows = props.data ?? [];
  const months = rows.map((row) => `M${row.month}`);
  return {
    animation: false,
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { left: 40, right: 20, top: 28, bottom: 40 },
    xAxis: { type: "category", data: months },
    yAxis: { type: "value", name: "kWh" },
    series: [
      { type: "bar", name: "PV", data: rows.map((row) => row.pv_kwh) },
      { type: "bar", name: "Wind", data: rows.map((row) => row.wind_kwh) },
      { type: "bar", name: "Battery", data: rows.map((row) => row.battery_discharge_kwh) },
      { type: "bar", name: "Diesel", data: rows.map((row) => row.diesel_kwh) },
      { type: "bar", name: "Grid Import", data: rows.map((row) => row.grid_import_kwh) },
      { type: "bar", name: "Grid Export", data: rows.map((row) => -row.grid_export_kwh) },
    ],
  };
});
</script>

<template>
  <div class="card">
    <h3 class="mb-2 text-lg font-semibold">Monthly Energy Mix</h3>
    <VChart :option="option" autoresize :style="{ height }" />
  </div>
</template>
