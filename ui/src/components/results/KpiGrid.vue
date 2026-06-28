<script setup lang="ts">
import { computed } from "vue";

import KpiCard from "@/components/results/KpiCard.vue";
import type { KpiSummary, SizingRow } from "@/api/types";

const props = defineProps<{
  kpis: KpiSummary | null;
  sizing?: SizingRow[] | null;
}>();

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Fractions (0–1) in the contract are rendered as percentages. */
function pct(value: unknown): number | null {
  const n = num(value);
  return n === null ? null : n * 100;
}

/** Component sizes come from the sizing table, not the KPI payload. */
function sizeOf(component: string): number | null {
  const row = props.sizing?.find((r) => r.component === component);
  return row && row.capacity > 0 ? row.capacity : null;
}

const cards = computed(() => {
  const k = props.kpis;
  return [
    { label: "LCOE", unit: "/kWh", value: num(k?.lcoe) },
    { label: "NPC", unit: "", value: num(k?.npc) },
    { label: "RE Fraction", unit: "%", value: pct(k?.renewable_fraction) },
    { label: "LPSP", unit: "%", value: pct(k?.lpsp) },
    { label: "CO₂", unit: "kg/yr", value: num(k?.total_emissions_kg) },
    { label: "PV", unit: "kW", value: sizeOf("pv") },
    { label: "Battery", unit: "kWh", value: sizeOf("battery_energy") },
    { label: "Diesel", unit: "kW", value: sizeOf("diesel_generator") },
  ];
});
</script>

<template>
  <div class="grid gap-3 md:grid-cols-2">
    <KpiCard
      v-for="card in cards"
      :key="card.label"
      :label="card.label"
      :value="card.value"
      :unit="card.unit"
    />
  </div>
</template>
