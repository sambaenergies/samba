<script setup lang="ts">
import { computed } from "vue";

import { COMPONENT_FIELDS } from "@/components/scenario/componentFields";
import { useScenarioStore } from "@/stores/scenario";
import { toNumberOrNull } from "@/utils/forms";

const props = defineProps<{
  name: string;
}>();

const scenario = useScenarioStore();

const friendlyName = computed(() =>
  props.name.replace(/_/g, " ").replace(/\b\w/g, (match: string) => match.toUpperCase()),
);

// Components are heterogeneous; bind dynamically against the draft object.
const state = computed(
  () => scenario.draft.components[props.name as keyof typeof scenario.draft.components] as Record<string, unknown>,
);

const fields = computed(() => COMPONENT_FIELDS[props.name] ?? []);

// The inverter is a required component (no `enabled` flag): always shown.
const hasToggle = computed(() => state.value != null && "enabled" in state.value);
const isOn = computed(() => !hasToggle.value || state.value?.enabled === true);
</script>

<template>
  <div v-if="state" class="rounded-lg border border-slate-200">
    <div class="flex items-center justify-between border-b border-slate-200 px-3 py-2">
      <h3 class="text-sm font-medium">{{ friendlyName }}</h3>
      <label v-if="hasToggle" class="inline-flex items-center gap-2 text-xs">
        <input v-model="state.enabled" type="checkbox" />
        <span>Enabled</span>
      </label>
      <span v-else class="text-xs text-slate-400">required</span>
    </div>

    <div v-if="isOn" class="grid grid-cols-2 gap-3 px-3 py-3">
      <div v-for="field in fields" :key="field.key">
        <label class="mb-1 block text-xs font-medium">{{ field.label }}</label>

        <select
          v-if="field.kind === 'select'"
          v-model="state[field.key]"
          class="w-full rounded border border-slate-300 px-2 py-1"
        >
          <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
        </select>

        <label v-else-if="field.kind === 'bool'" class="inline-flex items-center gap-2 py-1 text-xs">
          <input v-model="state[field.key]" type="checkbox" />
        </label>

        <input
          v-else-if="field.kind === 'text'"
          v-model="state[field.key]"
          type="text"
          class="w-full rounded border border-slate-300 px-2 py-1"
        />

        <input
          v-else
          :value="state[field.key]"
          type="number"
          :step="field.step ?? 'any'"
          class="w-full rounded border border-slate-300 px-2 py-1"
          @input="state[field.key] = toNumberOrNull($event)"
        />
      </div>
    </div>
  </div>
</template>
