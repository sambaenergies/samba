<script setup lang="ts">
import { useScenarioStore } from "@/stores/scenario";

const scenario = useScenarioStore();
</script>

<template>
  <section id="location" class="card space-y-4">
    <h2 class="text-lg font-semibold">Location</h2>

    <div class="grid grid-cols-2 gap-3">
      <div>
        <label class="mb-1 block text-sm font-medium" for="location-lat">Latitude</label>
        <input
          id="location-lat"
          v-model.number="scenario.draft.location.latitude"
          type="number"
          min="-90"
          max="90"
          step="0.0001"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="location-lon">Longitude</label>
        <input
          id="location-lon"
          v-model.number="scenario.draft.location.longitude"
          type="number"
          min="-180"
          max="180"
          step="0.0001"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="location-altitude">Altitude (m)</label>
        <input
          id="location-altitude"
          v-model.number="scenario.draft.location.altitude_m"
          type="number"
          min="0"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="location-timezone">Timezone</label>
        <input
          id="location-timezone"
          v-model="scenario.draft.location.timezone"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
          placeholder="e.g. Europe/London"
        />
      </div>
    </div>

    <div class="rounded-md border border-slate-200 p-3">
      <h3 class="mb-2 text-sm font-medium">Weather source</h3>
      <select
        v-model="scenario.draft.weather.source"
        class="w-full rounded-md border border-slate-300 px-3 py-2"
      >
        <option value="csv">CSV file</option>
        <option value="nsrdb">NSRDB (NREL API)</option>
      </select>
      <input
        v-if="scenario.draft.weather.source === 'csv'"
        v-model="scenario.draft.weather.csv_path"
        class="mt-2 w-full rounded-md border border-slate-300 px-3 py-2"
        placeholder="Path to weather CSV (GHI, DHI, DNI, Temp, WindSpeed)"
      />
      <template v-if="scenario.draft.weather.source === 'nsrdb'">
        <input
          v-model="scenario.draft.weather.nsrdb_api_key"
          class="mt-2 w-full rounded-md border border-slate-300 px-3 py-2"
          placeholder="NSRDB API key"
        />
        <input
          v-model="scenario.draft.weather.nsrdb_email"
          class="mt-2 w-full rounded-md border border-slate-300 px-3 py-2"
          placeholder="NSRDB account email"
        />
      </template>
    </div>
  </section>
</template>
