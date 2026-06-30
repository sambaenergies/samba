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

	const [{ listen }, { invoke }] = await Promise.all([
		import("@tauri-apps/api/event"),
		import("@tauri-apps/api/core"),
	]);

	const connection = useConnectionStore(pinia);
	const initialUrl = await invoke<string | null>("get_backend_url");
	if (initialUrl) {
		connection.setBackendUrl(initialUrl);
		await connection.checkConnection();
	}

	await listen<string>("samba-ready", async (event) => {
		connection.setBackendUrl(event.payload);
		await connection.checkConnection();
	});

	// If the bundled backend fails to start, surface it instead of spinning on
	// the initial "checking" state forever.
	await listen<string>("samba-error", (event) => {
		console.error("SAMBA backend failed to start:", event.payload);
		connection.status = "unreachable";
	});

	window.addEventListener("beforeunload", () => {
		void invoke("samba_shutdown");
	});
}

void setupTauriBackend().finally(() => {
	app.mount("#app");
});
