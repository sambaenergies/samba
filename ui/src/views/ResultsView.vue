<script setup lang="ts">
import { defineAsyncComponent, onMounted, onUnmounted, ref } from "vue";
import { RouterLink } from "vue-router";

import ArtifactList from "@/components/results/ArtifactList.vue";
import CashflowTable from "@/components/results/CashflowTable.vue";
import DispatchControls from "@/components/results/DispatchControls.vue";
import KpiGrid from "@/components/results/KpiGrid.vue";
import SizingTable from "@/components/results/SizingTable.vue";
import { useResultsStore } from "@/stores/results";

const DispatchChart = defineAsyncComponent(() => import("@/components/results/DispatchChart.vue"));
const MonthlyBarChart = defineAsyncComponent(() => import("@/components/results/MonthlyBarChart.vue"));
const NpvChart = defineAsyncComponent(() => import("@/components/results/NpvChart.vue"));
const CostBreakdownPie = defineAsyncComponent(() => import("@/components/results/CostBreakdownPie.vue"));

const props = defineProps<{ runId?: string }>();
const results = useResultsStore();

const activeTab = ref<"summary" | "dispatch" | "economics" | "downloads">("summary");
const zoomPreset = ref<"week1" | "peak" | "full">("week1");
const visibleSeries = ref<string[]>(["pv_gen", "wt_gen", "dg_gen", "grid_buy", "eload", "batt_soc"]);

function setZoomPreset(preset: "week1" | "peak" | "full") {
  zoomPreset.value = preset;
}

function setVisibleSeries(series: string[]) {
  visibleSeries.value = series;
}

onMounted(async () => {
  if (props.runId) {
    await results.loadResult(props.runId);
  }
});

onUnmounted(() => {
  results.stopPolling();
});
</script>

<template>
  <div class="space-y-4">
    <header class="card flex flex-wrap items-center justify-between gap-2">
      <div>
        <h1 class="text-2xl font-semibold">Results</h1>
        <p v-if="runId" class="text-xs text-slate-500">Run ID: {{ runId }}</p>
      </div>
      <div class="flex gap-2">
        <RouterLink class="btn" to="/jobs">Back to Jobs</RouterLink>
        <RouterLink class="btn" to="/editor">New Scenario</RouterLink>
      </div>
    </header>

    <section class="card">
      <div class="mb-2 flex items-center gap-2 text-sm">
        <span class="rounded bg-slate-100 px-2 py-1">{{ results.job?.status ?? "loading" }}</span>
        <span v-if="results.job?.solve_time_s != null" class="text-slate-500">
          solved in {{ results.job.solve_time_s.toFixed(1) }}s
        </span>
      </div>

      <div v-if="results.job?.status === 'running' || results.job?.status === 'pending'" class="space-y-2">
        <p class="text-sm text-slate-600">Solver running…</p>
        <!-- The LP solve has no incremental progress signal; show an indeterminate bar. -->
        <div class="h-2 w-full overflow-hidden rounded bg-slate-200">
          <div class="h-2 w-1/2 animate-pulse rounded bg-slate-800" />
        </div>
      </div>

      <div v-if="results.job?.status === 'failed'" class="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
        {{ results.job.error ?? "Run failed." }}
      </div>
    </section>

    <section v-if="results.job?.status === 'completed'" class="space-y-3">
      <div class="flex flex-wrap gap-2">
        <button class="btn" :class="activeTab === 'summary' ? 'bg-slate-900 text-white' : ''" @click="activeTab = 'summary'">Summary</button>
        <button class="btn" :class="activeTab === 'dispatch' ? 'bg-slate-900 text-white' : ''" @click="activeTab = 'dispatch'">Dispatch</button>
        <button class="btn" :class="activeTab === 'economics' ? 'bg-slate-900 text-white' : ''" @click="activeTab = 'economics'">Economics</button>
        <button class="btn" :class="activeTab === 'downloads' ? 'bg-slate-900 text-white' : ''" @click="activeTab = 'downloads'">Downloads</button>
      </div>

      <div v-if="activeTab === 'summary'" class="space-y-3">
        <KpiGrid :kpis="results.kpis" :sizing="results.sizing" />
        <SizingTable :rows="results.sizing" :npc-total="(results.kpis?.npc as number | null | undefined) ?? null" />
      </div>

      <div v-if="activeTab === 'dispatch'" class="space-y-3">
        <DispatchControls
          :selected-series="visibleSeries"
          @set-zoom="setZoomPreset"
          @update:series="setVisibleSeries"
        />
        <DispatchChart :data="results.dispatch" :zoom-preset="zoomPreset" :visible-series="visibleSeries" />
        <MonthlyBarChart :data="results.monthlySummary" />
      </div>

      <div v-if="activeTab === 'economics'" class="grid gap-3 lg:grid-cols-2">
        <CashflowTable :rows="results.cashflows" />
        <div class="space-y-3">
          <NpvChart :rows="results.cashflows" />
          <CostBreakdownPie :rows="results.cashflows" />
        </div>
      </div>

      <div v-if="activeTab === 'downloads'" class="card">
        <ArtifactList :run-id="runId ?? ''" :artifacts="results.availableArtifacts" />
      </div>
    </section>
  </div>
</template>
