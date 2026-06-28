<script setup lang="ts">
import { useScenarioStore } from "@/stores/scenario";
import { toNumberOrNull } from "@/utils/forms";

const scenario = useScenarioStore();

function error(path: string[]) {
  return scenario.errorAt(path);
}
</script>

<template>
  <section id="project" class="card space-y-4">
    <h2 class="text-lg font-semibold">Project</h2>

    <div>
      <label class="mb-1 block text-sm font-medium" for="project-name">Name</label>
      <input
        id="project-name"
        v-model="scenario.draft.project.name"
        class="w-full rounded-md border px-3 py-2"
        :class="error(['project', 'name']) ? 'border-red-500' : 'border-slate-300'"
      />
      <p v-if="error(['project', 'name'])" class="mt-1 text-xs text-red-600">
        {{ error(["project", "name"])?.message }}
      </p>
    </div>

    <div class="grid grid-cols-2 gap-3">
      <div>
        <label class="mb-1 block text-sm font-medium" for="project-year">Calendar year</label>
        <input
          id="project-year"
          v-model.number="scenario.draft.project.year"
          type="number"
          min="1"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="project-lifetime">Lifetime (years)</label>
        <input
          id="project-lifetime"
          v-model.number="scenario.draft.project.lifetime_years"
          type="number"
          min="1"
          max="40"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="project-discount">Discount rate (nominal)</label>
        <input
          id="project-discount"
          v-model.number="scenario.draft.project.discount_rate_nominal"
          type="number"
          min="0"
          max="1"
          step="0.001"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="project-inflation">Inflation rate</label>
        <input
          id="project-inflation"
          v-model.number="scenario.draft.project.inflation_rate"
          type="number"
          min="0"
          max="1"
          step="0.001"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="project-incentive">RE incentive rate</label>
        <input
          id="project-incentive"
          v-model.number="scenario.draft.project.re_incentive_rate"
          type="number"
          min="0"
          max="1"
          step="0.01"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="project-currency">Currency</label>
        <select
          id="project-currency"
          v-model="scenario.draft.project.currency"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        >
          <option>USD</option>
          <option>EUR</option>
          <option>GBP</option>
          <option>JPY</option>
          <option>AUD</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="project-capex-year">Capex year</label>
        <input
          id="project-capex-year"
          v-model.number="scenario.draft.project.capex_year"
          type="number"
          min="0"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium" for="project-budget">Budget (blank = unlimited)</label>
        <input
          id="project-budget"
          :value="scenario.draft.project.budget"
          type="number"
          min="0"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
          @input="scenario.draft.project.budget = toNumberOrNull($event)"
        />
      </div>
    </div>
  </section>
</template>
