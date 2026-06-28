<script setup lang="ts">
import { useScenarioStore } from "@/stores/scenario";

const scenario = useScenarioStore();
</script>

<template>
  <section id="objective" class="card space-y-4">
    <h2 class="text-lg font-semibold">Objective</h2>

    <div v-if="scenario.draft.objective">
      <label class="mb-1 block text-sm font-medium">Type</label>
      <select v-model="scenario.draft.objective.type" class="w-full rounded-md border border-slate-300 px-3 py-2">
        <option value="cost">cost (minimise NPC)</option>
        <option value="cost_and_emissions">cost_and_emissions</option>
      </select>
    </div>

    <div v-if="scenario.draft.objective && scenario.draft.objective.type === 'cost_and_emissions'">
      <label class="mb-1 block text-sm font-medium">Emissions weight ($/kg CO₂)</label>
      <input
        v-model.number="scenario.draft.objective.emissions_weight"
        type="number"
        min="0"
        step="0.001"
        class="w-full rounded-md border border-slate-300 px-3 py-2"
      />
    </div>
  </section>
</template>
