<script setup lang="ts">
import { computed } from "vue";

import { useScenarioStore } from "@/stores/scenario";

const scenario = useScenarioStore();

const BUY_TYPES = [
  "flat",
  "tou",
  "tiered",
  "seasonal",
  "seasonal_tiered",
  "monthly",
  "monthly_tiered",
  "ul_tou",
] as const;

const sellEnabled = computed({
  get: () => scenario.draft.tariff.sell != null,
  set: (v: boolean) => {
    scenario.draft.tariff.sell = v ? { type: "flat", rate_per_kwh: 0.05 } : null;
  },
});

const serviceEnabled = computed({
  get: () => scenario.draft.tariff.service_charge != null,
  set: (v: boolean) => {
    scenario.draft.tariff.service_charge = v ? { type: "flat", monthly_flat: 10.0 } : null;
  },
});

const isAdvancedBuy = computed(
  () => scenario.draft.tariff.buy.type !== "flat" && scenario.draft.tariff.buy.type !== "ul_tou",
);
</script>

<template>
  <section id="tariff" class="card space-y-4">
    <h2 class="text-lg font-semibold">Tariff</h2>

    <div class="grid grid-cols-2 gap-3">
      <div>
        <label class="mb-1 block text-sm font-medium">Buy type</label>
        <select v-model="scenario.draft.tariff.buy.type" class="w-full rounded-md border border-slate-300 px-3 py-2">
          <option v-for="t in BUY_TYPES" :key="t" :value="t">{{ t }}</option>
        </select>
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium">Buy rate /kWh</label>
        <input
          v-model.number="scenario.draft.tariff.buy.rate_per_kwh"
          type="number"
          min="0"
          step="0.0001"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
    </div>

    <p v-if="isAdvancedBuy" class="rounded bg-amber-50 px-3 py-2 text-xs text-amber-700">
      “{{ scenario.draft.tariff.buy.type }}” needs a tou/tier/seasonal schedule. Configure it via
      <strong>Import YAML</strong>; this form edits the flat base rate only.
    </p>

    <div class="rounded-md border border-slate-200 p-3">
      <label class="inline-flex items-center gap-2 text-sm font-medium">
        <input v-model="sellEnabled" type="checkbox" />
        <span>Sell / feed-in tariff</span>
      </label>
      <div v-if="sellEnabled && scenario.draft.tariff.sell" class="mt-3 grid grid-cols-2 gap-3">
        <div>
          <label class="mb-1 block text-xs font-medium">Type</label>
          <select v-model="scenario.draft.tariff.sell.type" class="w-full rounded border border-slate-300 px-2 py-1">
            <option value="flat">flat</option>
            <option value="tou">tou</option>
            <option value="monthly">monthly</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium">Rate /kWh</label>
          <input
            v-model.number="scenario.draft.tariff.sell.rate_per_kwh"
            type="number"
            min="0"
            step="0.0001"
            class="w-full rounded border border-slate-300 px-2 py-1"
          />
        </div>
      </div>
    </div>

    <div class="rounded-md border border-slate-200 p-3">
      <label class="inline-flex items-center gap-2 text-sm font-medium">
        <input v-model="serviceEnabled" type="checkbox" />
        <span>Monthly service charge</span>
      </label>
      <div v-if="serviceEnabled && scenario.draft.tariff.service_charge" class="mt-3 grid grid-cols-2 gap-3">
        <div>
          <label class="mb-1 block text-xs font-medium">Type</label>
          <select
            v-model="scenario.draft.tariff.service_charge.type"
            class="w-full rounded border border-slate-300 px-2 py-1"
          >
            <option value="flat">flat</option>
            <option value="tiered_kwh">tiered_kwh</option>
          </select>
        </div>
        <div>
          <label class="mb-1 block text-xs font-medium">Monthly flat</label>
          <input
            v-model.number="scenario.draft.tariff.service_charge.monthly_flat"
            type="number"
            min="0"
            step="0.01"
            class="w-full rounded border border-slate-300 px-2 py-1"
          />
        </div>
      </div>
    </div>
  </section>
</template>
