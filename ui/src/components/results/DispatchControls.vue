<script setup lang="ts">
const presets = [
  { id: "week1", label: "Week 1" },
  { id: "peak", label: "Peak Week" },
  { id: "full", label: "Full Year" },
] as const;

const allSeries = ["pv_gen", "wt_gen", "dg_gen", "grid_buy", "eload", "batt_soc"];

defineProps<{
  selectedSeries: string[];
}>();

const emit = defineEmits<{
  "update:series": [series: string[]];
  "set-zoom": [preset: "week1" | "peak" | "full"];
}>();

function updateSeries(name: string, enabled: boolean, selectedSeries: string[]) {
  if (enabled) {
    emit("update:series", [...new Set([...selectedSeries, name])]);
    return;
  }
  emit("update:series", selectedSeries.filter((series) => series !== name));
}

function onSeriesChange(name: string, event: Event, selectedSeries: string[]) {
  const target = event.target as HTMLInputElement;
  updateSeries(name, target.checked, selectedSeries);
}
</script>

<template>
  <div class="card space-y-3">
    <div class="flex flex-wrap gap-2">
      <button v-for="preset in presets" :key="preset.id" class="btn" @click="emit('set-zoom', preset.id)">
        {{ preset.label }}
      </button>
    </div>
    <div class="flex flex-wrap gap-3 text-sm">
      <label v-for="series in allSeries" :key="series" class="inline-flex items-center gap-2">
        <input
          type="checkbox"
          :checked="selectedSeries.includes(series)"
          @change="onSeriesChange(series, $event, selectedSeries)"
        />
        <span>{{ series }}</span>
      </label>
    </div>
  </div>
</template>
