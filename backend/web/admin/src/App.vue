<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

import AdminLayout from "@/layouts/AdminLayout.vue";
import AuthLayout from "@/layouts/AuthLayout.vue";

const route = useRoute();

const layoutComponent = computed(() => {
  if (route.meta.layout === "auth") return AuthLayout;
  if (route.meta.layout === "none") return null;
  return AdminLayout;
});
</script>

<template>
  <component v-if="layoutComponent" :is="layoutComponent">
    <RouterView />
  </component>
  <RouterView v-else />
</template>
