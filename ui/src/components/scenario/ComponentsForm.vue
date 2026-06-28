<script setup lang="ts">
import ComponentCard from "@/components/scenario/ComponentCard.vue";
import { useScenarioStore } from "@/stores/scenario";

const scenario = useScenarioStore();
</script>

<template>
  <section id="components" class="card space-y-4">
    <h2 class="text-lg font-semibold">Components</h2>
    <div class="space-y-3">
      <ComponentCard v-for="name in scenario.componentOrder" :key="name" :name="name" />
    </div>
  </section>
</template>
