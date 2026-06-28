import { defineStore } from "pinia";
import { useStorage } from "@vueuse/core";

import { fetchHealth } from "@/api/health";

export type ConnectionStatus = "checking" | "connected" | "unreachable";

export const useConnectionStore = defineStore("connection", {
  state: () => ({
    backendUrl: useStorage("samba.backendUrl", "http://127.0.0.1:8000").value,
    apiKey: useStorage<string | null>("samba.apiKey", null).value,
    status: "checking" as ConnectionStatus,
    version: null as string | null,
    solver: null as string | null,
    pollTimer: null as ReturnType<typeof setInterval> | null,
  }),
  actions: {
    async checkConnection() {
      this.status = "checking";
      try {
        const health = await fetchHealth();
        this.version = health.version;
        this.solver = health.solver;
        this.status = "connected";
      } catch {
        this.status = "unreachable";
      }
    },
    setBackendUrl(value: string) {
      this.backendUrl = value;
      useStorage("samba.backendUrl", "").value = value;
    },
    setApiKey(value: string | null) {
      this.apiKey = value;
      useStorage<string | null>("samba.apiKey", null).value = value;
    },
    startPolling() {
      if (this.pollTimer) {
        return;
      }
      void this.checkConnection();
      this.pollTimer = setInterval(() => {
        void this.checkConnection();
      }, 30_000);
    },
    stopPolling() {
      if (!this.pollTimer) {
        return;
      }
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    },
  },
});
