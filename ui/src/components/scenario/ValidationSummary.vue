<script setup lang="ts">
import { computed, ref } from "vue";
import { useScenarioStore } from "@/stores/scenario";

const scenario = useScenarioStore();
const open = ref(false);

const title = computed(() => {
  if (scenario.validationPending) {
    return "Validating…";
  }
  if (!scenario.validationErrors.length) {
    return "Valid ✓";
  }
  const errors = scenario.errorCount;
  const warnings = scenario.warningCount;
  if (warnings && errors) {
    return `${errors} errors, ${warnings} warnings`;
  }
  if (errors) {
    return `${errors} errors`;
  }
  return `${warnings} warnings`;
});

function jumpTo(errorPath: string[]) {
  const section = errorPath[0] ?? "project";
  document.getElementById(section)?.scrollIntoView({ behavior: "smooth", block: "start" });
}
</script>

<template>
  <section class="card" aria-live="polite">
    <div class="flex items-center justify-between gap-3">
      <p class="text-sm font-medium">{{ title }}</p>
      <button class="btn" type="button" @click="open = !open">{{ open ? "Hide" : "Show" }} details</button>
    </div>

    <div v-if="open" class="mt-3 space-y-2">
      <div v-if="!scenario.validationErrors.length" class="text-sm text-emerald-700">
        No validation issues.
      </div>
      <button
        v-for="(error, idx) in scenario.validationErrors"
        :key="`${error.path.join('.')}-${idx}`"
        type="button"
        class="w-full rounded border border-slate-200 px-3 py-2 text-left text-sm hover:bg-slate-50"
        @click="jumpTo(error.path)"
      >
        <span
          class="mr-2 inline-block rounded px-1.5 py-0.5 text-xs"
          :class="error.severity === 'warning' ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'"
        >
          {{ error.severity }}
        </span>
        <span class="font-medium">{{ error.path.join(".") || "scenario" }}</span>
        <span class="text-slate-600"> — {{ error.message }}</span>
      </button>
    </div>
  </section>
</template>
