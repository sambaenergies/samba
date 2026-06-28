<script setup lang="ts">
import { computed } from "vue";

import { useScenarioStore } from "@/stores/scenario";
import { toNumberOrNull } from "@/utils/forms";

const scenario = useScenarioStore();

const LOAD_SOURCES = [
  "hourly_csv",
  "daily_csv",
  "monthly_total",
  "monthly_hourly_average",
  "annual_hourly_average",
  "annual_daily_average",
  "generic_monthly",
  "generic_annual",
  "generic_annual_total",
  "generic",
  "template",
] as const;

const needsCsv = computed(() => (scenario.draft.load.source ?? "").includes("csv"));
const needsAnnualKwh = computed(() => (scenario.draft.load.source ?? "").startsWith("generic_annual"));
const thermalEnabled = computed({
  get: () => scenario.draft.load.thermal?.enabled ?? false,
  set: (v: boolean) => {
    if (!scenario.draft.load.thermal) {
      scenario.draft.load.thermal = {
        enabled: v,
        source: "degree_day",
        building_ua_kw_per_k: 0.5,
        heating_setpoint_c: 20.0,
        cooling_setpoint_c: 26.0,
        distribution_efficiency: 0.95,
      };
    } else {
      scenario.draft.load.thermal.enabled = v;
    }
  },
});
</script>

<template>
  <section id="load" class="card space-y-4">
    <h2 class="text-lg font-semibold">Load</h2>

    <div class="grid grid-cols-2 gap-3">
      <div>
        <label class="mb-1 block text-sm font-medium" for="load-source">Source</label>
        <select
          id="load-source"
          v-model="scenario.draft.load.source"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        >
          <option v-for="src in LOAD_SOURCES" :key="src" :value="src">{{ src }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="load-scale">Scale factor</label>
        <input
          id="load-scale"
          v-model.number="scenario.draft.load.scale_factor"
          type="number"
          min="0"
          step="0.1"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div v-if="needsCsv" class="col-span-2">
        <label class="mb-1 block text-sm font-medium" for="load-csv">CSV path</label>
        <input
          id="load-csv"
          v-model="scenario.draft.load.csv_path"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
          placeholder="content/load_residential_8760.csv"
        />
      </div>
      <div v-if="needsAnnualKwh">
        <label class="mb-1 block text-sm font-medium" for="load-annual">Annual energy (kWh)</label>
        <input
          id="load-annual"
          :value="scenario.draft.load.annual_kwh"
          type="number"
          min="0"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
          @input="scenario.draft.load.annual_kwh = toNumberOrNull($event)"
        />
      </div>
    </div>

    <div class="rounded-md border border-slate-200 p-3">
      <label class="inline-flex items-center gap-2 text-sm font-medium">
        <input v-model="thermalEnabled" type="checkbox" />
        <span>Thermal load (heating / cooling)</span>
      </label>

      <div v-if="thermalEnabled && scenario.draft.load.thermal" class="mt-3 grid grid-cols-2 gap-3">
        <div>
          <label class="mb-1 block text-xs font-medium">Source</label>
          <select
            v-model="scenario.draft.load.thermal.source"
            class="w-full rounded border border-slate-300 px-2 py-1"
          >
            <option value="degree_day">degree_day</option>
            <option value="csv">csv</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium">Building UA (kW/K)</label>
          <input
            v-model.number="scenario.draft.load.thermal.building_ua_kw_per_k"
            type="number"
            min="0"
            step="0.1"
            class="w-full rounded border border-slate-300 px-2 py-1"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium">Heating setpoint (°C)</label>
          <input
            v-model.number="scenario.draft.load.thermal.heating_setpoint_c"
            type="number"
            class="w-full rounded border border-slate-300 px-2 py-1"
          />
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium">Cooling setpoint (°C)</label>
          <input
            v-model.number="scenario.draft.load.thermal.cooling_setpoint_c"
            type="number"
            class="w-full rounded border border-slate-300 px-2 py-1"
          />
        </div>
      </div>
    </div>
  </section>
</template>
