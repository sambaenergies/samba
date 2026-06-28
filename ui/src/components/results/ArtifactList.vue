<script setup lang="ts">
import JSZip from "jszip";

import { fetchArtifact } from "@/api/artifacts";

const props = defineProps<{
  runId: string;
  artifacts: string[];
}>();

async function downloadOne(filename: string) {
  const blob = await fetchArtifact(props.runId, filename);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

async function downloadAll() {
  const zip = new JSZip();

  for (const filename of props.artifacts) {
    const blob = await fetchArtifact(props.runId, filename);
    zip.file(filename, blob);
  }

  const zipped = await zip.generateAsync({ type: "blob" });
  const url = URL.createObjectURL(zipped);
  const link = document.createElement("a");
  link.href = url;
  link.download = `run-${props.runId}-artifacts.zip`;
  link.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex justify-end">
      <button class="btn" type="button" :disabled="!artifacts.length" @click="downloadAll">Download All</button>
    </div>
    <div class="rounded-lg border border-slate-200">
      <div v-for="artifact in artifacts" :key="artifact" class="flex items-center justify-between border-b border-slate-100 px-3 py-2 last:border-b-0">
        <span class="text-sm">{{ artifact }}</span>
        <button class="btn" type="button" @click="downloadOne(artifact)">Download</button>
      </div>
      <p v-if="!artifacts.length" class="px-3 py-4 text-sm text-slate-500">No artifacts listed for this run.</p>
    </div>
  </div>
</template>
