<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

import { useAppStore } from "@/stores/app";
import { useAuthStore } from "@/stores/auth";
import { Expand } from "@element-plus/icons-vue";

const route = useRoute();
const appStore = useAppStore();
const authStore = useAuthStore();

const title = computed(() => String(route.meta.title || "芸熙烘焙后台"));
</script>

<template>
  <header class="topbar">
    <div class="topbar__left">
      <el-button
        text
        class="topbar__menu-btn"
        @click="appStore.toggleSidebar"
      >
        <el-icon size="20"><Expand /></el-icon>
      </el-button>
      <div>
        <div class="topbar__title">{{ title }}</div>
      </div>
    </div>
    <div class="topbar__right">
      <span class="topbar__user">
        {{ authStore.profile?.name || "管理员" }}
      </span>
    </div>
  </header>
</template>
