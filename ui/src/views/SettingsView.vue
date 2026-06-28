<script setup lang="ts">
import { ref } from "vue";
import { useConnectionStore } from "@/stores/connection";

const connection = useConnectionStore();
const backendUrl = ref(connection.backendUrl);
const apiKey = ref(connection.apiKey ?? "");

function save() {
  connection.setBackendUrl(backendUrl.value.trim());
  connection.setApiKey(apiKey.value.trim() || null);
}
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-semibold">Settings</h1>

    <section class="card space-y-3">
      <div>
        <label class="mb-1 block text-sm font-medium">Backend URL</label>
        <input v-model="backendUrl" class="w-full rounded-md border border-slate-300 px-3 py-2" />
      </div>
      <div>
        <label class="mb-1 block text-sm font-medium">API Key</label>
        <input
          v-model="apiKey"
          type="password"
          class="w-full rounded-md border border-slate-300 px-3 py-2"
          placeholder="optional"
        />
      </div>
      <div class="flex gap-2">
        <button class="btn" @click="save">Save</button>
        <button class="btn" @click="connection.checkConnection">Test Connection</button>
      </div>
      <p class="text-sm">Status: <strong class="capitalize">{{ connection.status }}</strong></p>
    </section>
  </div>
</template>
