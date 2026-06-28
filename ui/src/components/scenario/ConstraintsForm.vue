<script setup lang="ts">
import { useScenarioStore } from "@/stores/scenario";
import { toNumberOrNull } from "@/utils/forms";

const scenario = useScenarioStore();
</script>

<template>
  <section id="constraints" class="card space-y-4">
    <h2 class="text-lg font-semibold">Constraints</h2>
    <p class="text-sm text-slate-600">Constraints are enforced as hard optimization limits.</p>

    <div v-if="scenario.draft.constraints" class="grid grid-cols-2 gap-3">
      <div>
        <label class="mb-1 block text-sm font-medium" for="constraint-lpsp">Max LPSP (0-1)</label>
        <input
          id="constraint-lpsp"
          v-model.number="scenario.draft.constraints.max_lpsp"
          type="number"
          min="0"
          max="1"
          step="0.001"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="constraint-renewable">Min renewable fraction (0-1)</label>
        <input
          id="constraint-renewable"
          v-model.number="scenario.draft.constraints.min_renewable_fraction"
          type="number"
          min="0"
          max="1"
          step="0.001"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="constraint-diesel">Max annual diesel (L, blank = none)</label>
        <input
          id="constraint-diesel"
          :value="scenario.draft.constraints.max_annual_diesel_l"
          type="number"
          min="0"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
          @input="scenario.draft.constraints.max_annual_diesel_l = toNumberOrNull($event)"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="constraint-cycles">Max battery cycles/yr (blank = none)</label>
        <input
          id="constraint-cycles"
          :value="scenario.draft.constraints.max_battery_cycles_yr"
          type="number"
          min="0"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
          @input="scenario.draft.constraints.max_battery_cycles_yr = toNumberOrNull($event)"
        />
      </div>
      <div class="col-span-2">
        <label class="inline-flex items-center gap-2 text-sm font-medium">
          <input v-model="scenario.draft.constraints.force_grid_disconnect" type="checkbox" />
          <span>Force grid disconnect (treat as off-grid)</span>
        </label>
      </div>
    </div>
  </section>
</template>
