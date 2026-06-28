import { createRouter, createWebHashHistory, createWebHistory } from "vue-router";

import HomeView from "@/views/HomeView.vue";
import EditorView from "@/views/EditorView.vue";
import JobsView from "@/views/JobsView.vue";
import ResultsView from "@/views/ResultsView.vue";
import SettingsView from "@/views/SettingsView.vue";
import NotFoundView from "@/views/NotFoundView.vue";
import { useConnectionStore } from "@/stores/connection";

const history = __APP_MODE__ === "tauri" ? createWebHashHistory() : createWebHistory();

export const router = createRouter({
  history,
  routes: [
    { path: "/", name: "home", component: HomeView },
    { path: "/editor", name: "editor", component: EditorView },
    { path: "/jobs", name: "jobs", component: JobsView },
    { path: "/results/:runId", name: "results", component: ResultsView, props: true },
    { path: "/settings", name: "settings", component: SettingsView },
    { path: "/:pathMatch(.*)*", name: "404", component: NotFoundView },
  ],
});

router.beforeEach((to) => {
  if (__APP_MODE__ === "tauri") {
    return true;
  }

  const connection = useConnectionStore();
  const needsBackend = to.path.startsWith("/editor") || to.path.startsWith("/jobs") || to.path.startsWith("/results");

  if (needsBackend && !connection.backendUrl.trim()) {
    return "/settings";
  }

  return true;
});
