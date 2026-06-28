<script setup lang="ts">
const sections = [
  { id: "project", label: "Project" },
  { id: "location", label: "Location" },
  { id: "load", label: "Load" },
  { id: "components", label: "Components" },
  { id: "tariff", label: "Tariff" },
  { id: "constraints", label: "Constraints" },
  { id: "objective", label: "Objective" },
] as const;

defineProps<{
  activeSection: string;
  sectionErrorCounts: Record<string, number>;
}>();

const emit = defineEmits<{
  navigate: [sectionId: string];
}>();
</script>

<template>
  <aside class="w-52 shrink-0 rounded-xl border border-slate-200 bg-white p-3">
    <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-600">Sections</h2>
    <ul class="space-y-1">
      <li v-for="section in sections" :key="section.id">
        <button
          type="button"
          class="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm"
          :class="
            section.id === activeSection
              ? 'bg-slate-900 text-white'
              : 'text-slate-700 hover:bg-slate-100'
          "
          @click="emit('navigate', section.id)"
        >
          <span>{{ section.label }}</span>
          <span
            v-if="sectionErrorCounts[section.id]"
            class="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700"
          >
            {{ sectionErrorCounts[section.id] }}
          </span>
        </button>
      </li>
    </ul>
  </aside>
</template>
