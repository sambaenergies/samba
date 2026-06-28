<script setup lang="ts">
const links = [
  { to: "/", label: "Home" },
  { to: "/editor", label: "Editor" },
  { to: "/jobs", label: "Jobs" },
  { to: "/settings", label: "Settings" },
];
</script>

<template>
  <aside class="sticky top-0 h-screen w-56 shrink-0 overflow-y-auto border-r border-slate-200 bg-white p-4">
    <h2 class="mb-4 text-lg font-semibold">SAMBA</h2>
    <nav class="flex flex-col gap-1">
      <RouterLink
        v-for="link in links"
        :key="link.to"
        :to="link.to"
        class="rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
        active-class="bg-slate-900 text-white hover:bg-slate-900"
      >
        {{ link.label }}
      </RouterLink>
    </nav>
  </aside>
</template>
