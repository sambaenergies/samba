import { defineStore } from "pinia";
import { useStorage } from "@vueuse/core";

import { fetchHealth } from "@/api/health";
// The contract this UI build was generated against (vendored in ui/contract/).
import contractManifest from "../../contract/manifest.json";

export type ConnectionStatus = "checking" | "connected" | "unreachable" | "incompatible";

/** Major version segment, for SemVer-major compatibility comparison. */
function majorOf(version: string | null | undefined): string | null {
  return version ? version.split(".")[0] : null;
}

export const useConnectionStore = defineStore("connection", {
  state: () => ({
    backendUrl: useStorage("samba.backendUrl", "http://127.0.0.1:8000").value,
    apiKey: useStorage<string | null>("samba.apiKey", null).value,
    status: "checking" as ConnectionStatus,
    version: null as string | null,
    apiVersion: null as string | null,
    solver: null as string | null,
    pollTimer: null as ReturnType<typeof setInterval> | null,
  }),
  actions: {
    async checkConnection() {
      this.status = "checking";
      try {
        const health = await fetchHealth();
        this.version = health.version;
        this.apiVersion = health.api_version;
        this.solver = health.solver;
        // The backend reachable but speaking an incompatible API major is a
        // distinct, actionable state from "unreachable".
        const built = majorOf(contractManifest.api_version);
        this.status = majorOf(health.api_version) === built ? "connected" : "incompatible";
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
