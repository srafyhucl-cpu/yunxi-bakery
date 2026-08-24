<script setup lang="ts">
import { onMounted } from "vue";

import AppSidebar from "@/components/layout/AppSidebar.vue";
import BottomNav from "@/components/layout/BottomNav.vue";
import Topbar from "@/components/layout/Topbar.vue";
import PageContainer from "@/components/layout/PageContainer.vue";
import { useAuthStore } from "@/stores/auth";
import { useAppStore } from "@/stores/app";

const authStore = useAuthStore();
const appStore = useAppStore();

onMounted(async () => {
  if (!authStore.initialized) {
    try {
      await authStore.fetchProfile();
    } catch {
      authStore.clearProfile();
    }
  }
});
</script>

<template>
  <div class="admin-shell">
    <AppSidebar
      v-if="appStore.shouldShowSidebar"
      :open="appStore.sidebarOpen"
    />
    <div class="admin-shell__main">
      <Topbar />
      <PageContainer>
        <slot />
      </PageContainer>
    </div>
    <BottomNav v-if="appStore.isPhone" />
  </div>
</template>
