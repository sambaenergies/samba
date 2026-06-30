import { createApp } from "vue";
import { createPinia } from "pinia";
import { VueQueryPlugin, QueryClient } from "@tanstack/vue-query";

import App from "./App.vue";
import { router } from "@/router";
import { useConnectionStore } from "@/stores/connection";
import "./styles.css";

const app = createApp(App);
const queryClient = new QueryClient();
const pinia = createPinia();

app.use(pinia);
app.use(router);
app.use(VueQueryPlugin, { queryClient });

async function setupTauriBackend() {
	if (__APP_MODE__ !== "tauri") {
		return;
	}

	const { invoke } = await import("@tauri-apps/api/core");

	const connection = useConnectionStore(pinia);
	// The backend starts synchronously in the Rust `setup()` hook, before this
	// code runs, so its result is pulled (not received as an event, which would
	// have already fired and been lost).
	const backendUrl = await invoke<string | null>("get_backend_url");
	if (backendUrl) {
		connection.setBackendUrl(backendUrl);
		await connection.checkConnection();
	} else {
		// Backend failed to start: surface it instead of spinning on "checking".
		const startupError = await invoke<string | null>("get_startup_error");
		if (startupError) {
			console.error("SAMBA backend failed to start:", startupError);
		}
		connection.status = "unreachable";
	}

	window.addEventListener("beforeunload", () => {
		void invoke("samba_shutdown");
	});
}

void setupTauriBackend().finally(() => {
	app.mount("#app");
});
