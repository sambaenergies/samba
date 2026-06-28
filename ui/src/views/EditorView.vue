<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import SectionNav from "@/components/scenario/SectionNav.vue";
import ProjectForm from "@/components/scenario/ProjectForm.vue";
import LocationForm from "@/components/scenario/LocationForm.vue";
import LoadForm from "@/components/scenario/LoadForm.vue";
import ComponentsForm from "@/components/scenario/ComponentsForm.vue";
import TariffForm from "@/components/scenario/TariffForm.vue";
import ConstraintsForm from "@/components/scenario/ConstraintsForm.vue";
import ObjectiveForm from "@/components/scenario/ObjectiveForm.vue";
import ValidationSummary from "@/components/scenario/ValidationSummary.vue";
import { useJobsStore } from "@/stores/jobs";
import { useScenarioStore } from "@/stores/scenario";

const router = useRouter();
const jobs = useJobsStore();
const scenario = useScenarioStore();

const activeSection = ref("project");
const importing = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

const hasErrors = computed(() => scenario.errorCount > 0);
const autosaveText = computed(() => {
  if (!scenario.lastSavedAt) {
    return "Not saved yet";
  }
  return `Saved ${new Date(scenario.lastSavedAt).toLocaleTimeString()}`;
});

// Map a validation path's root key to an editor section id. Weather is edited
// inside the Location section; schema_version surfaces under Project.
const SECTION_OF: Record<string, string> = {
  weather: "location",
  schema_version: "project",
};

const sectionErrorCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const error of scenario.validationErrors) {
    const root = error.path[0] ?? "project";
    const section = SECTION_OF[root] ?? root;
    counts[section] = (counts[section] ?? 0) + 1;
  }
  return counts;
});

function scrollToSection(sectionId: string) {
  activeSection.value = sectionId;
  document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function triggerImportPicker() {
  fileInput.value?.click();
}

async function handleFileImport(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) {
    return;
  }

  importing.value = true;
  try {
    const text = await file.text();
    await scenario.importYaml(text);
  } finally {
    importing.value = false;
    input.value = "";
  }
}

async function copyYaml() {
  const yaml = scenario.exportYaml();
  await navigator.clipboard.writeText(yaml);
}

function downloadYaml() {
  const yaml = scenario.exportYaml();
  const blob = new Blob([yaml], { type: "application/yaml" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "scenario.yaml";
  link.click();
  URL.revokeObjectURL(url);
}

async function runScenario() {
  const runId = await jobs.submitCurrent();
  await router.push("/jobs");
  return runId;
}

onMounted(() => {
  void scenario.validateNow();
});

watch(
  () => scenario.draft,
  () => {
    scenario.touchDraft();
  },
  { deep: true },
);
</script>

<template>
  <div class="space-y-4">
    <header class="card flex flex-wrap items-center justify-between gap-2">
      <h1 class="text-2xl font-semibold">Scenario Editor</h1>
      <div class="flex flex-wrap gap-2">
        <input
          ref="fileInput"
          type="file"
          accept=".yaml,.yml"
          class="hidden"
          @change="handleFileImport"
        />
        <button class="btn" :disabled="importing" @click="triggerImportPicker">Import YAML</button>
        <button class="btn" @click="downloadYaml">Download YAML</button>
        <button class="btn" @click="copyYaml">Copy YAML</button>
        <button class="btn" @click="scenario.resetToDefaults">Reset</button>
        <button class="btn" :disabled="hasErrors || scenario.validationPending" @click="runScenario">Run</button>
      </div>
    </header>

    <div class="flex gap-4">
      <SectionNav :active-section="activeSection" :section-error-counts="sectionErrorCounts" @navigate="scrollToSection" />

      <div class="min-w-0 flex-1 space-y-4">
        <ProjectForm />
        <LocationForm />
        <LoadForm />
        <ComponentsForm />
        <TariffForm />
        <ConstraintsForm />
        <ObjectiveForm />
      </div>
    </div>

    <div class="grid gap-3 md:grid-cols-[1fr_auto] md:items-center">
      <ValidationSummary />
      <div class="text-xs text-slate-500">{{ autosaveText }}</div>
    </div>
  </div>
</template>
