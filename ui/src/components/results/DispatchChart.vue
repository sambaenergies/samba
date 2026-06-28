<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent, DataZoomComponent } from "echarts/components";

import type { DispatchData } from "@/api/types";

use([CanvasRenderer, LineChart, GridComponent, LegendComponent, TooltipComponent, DataZoomComponent]);

const props = withDefaults(
  defineProps<{
    data: DispatchData | null;
    height?: string;
    visibleSeries?: string[];
    zoomPreset?: "week1" | "peak" | "full";
  }>(),
  {
    height: "420px",
    visibleSeries: () => ["pv_gen", "wt_gen", "dg_gen", "grid_buy", "eload", "batt_soc"],
    zoomPreset: "week1",
  },
);

const zoomRange = computed(() => {
  if (props.zoomPreset === "full") {
    return { start: 0, end: 100 };
  }
  if (props.zoomPreset === "peak") {
    const loadSeries = props.data?.series.eload;
    if (!loadSeries || loadSeries.length <= 168) {
      return { start: 0, end: 2 };
    }

    let bestIndex = 0;
    let bestSum = -Infinity;
    let rolling = 0;

    for (let index = 0; index < loadSeries.length; index += 1) {
      rolling += loadSeries[index] ?? 0;
      if (index >= 168) {
        rolling -= loadSeries[index - 168] ?? 0;
      }
      if (index >= 167 && rolling > bestSum) {
        bestSum = rolling;
        bestIndex = index - 167;
      }
    }

    const start = (bestIndex / loadSeries.length) * 100;
    const end = ((bestIndex + 168) / loadSeries.length) * 100;
    return { start, end: Math.min(100, end) };
  }
  return { start: 0, end: 2 };
});

const series = computed(() => {
  if (!props.data) {
    return [];
  }

  return Object.entries(props.data.series)
    .filter(([name]) => props.visibleSeries.includes(name))
    .map(([name, values]) => ({
      name,
      type: "line",
      showSymbol: false,
      sampling: "lttb",
      smooth: true,
      yAxisIndex: name === "batt_soc" ? 1 : 0,
      data: props.data?.timestamps.map((timestamp, idx) => [new Date(timestamp).getTime(), values[idx] ?? 0]),
    }));
});

const option = computed(() => ({
  animation: false,
  tooltip: { trigger: "axis" },
  legend: { top: 0 },
  grid: { left: 40, right: 40, top: 32, bottom: 80 },
  xAxis: { type: "time" },
  yAxis: [
    { type: "value", name: "kW" },
    { type: "value", name: "SOC %" },
  ],
  dataZoom: [
    { type: "inside" },
    { type: "slider", start: zoomRange.value.start, end: zoomRange.value.end },
  ],
  series: series.value,
}));
</script>

<template>
  <div class="card">
    <h3 class="mb-2 text-lg font-semibold">Dispatch</h3>
    <VChart :option="option" autoresize :style="{ height }" />
  </div>
</template>
