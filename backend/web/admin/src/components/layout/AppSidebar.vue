<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

import { ADMIN_NAV_ITEMS } from "@/constants/adminNavigation";

const props = defineProps<{
  open: boolean;
}>();

const route = useRoute();

const activeKey = computed(() => route.meta.navKey);
</script>

<template>
  <aside
    class="app-sidebar"
    :class="{ 'app-sidebar--collapsed': !props.open }"
  >
    <div class="app-sidebar__brand">
      <span class="app-sidebar__title">
        <span>芸</span>
        <span class="app-sidebar__title-rest" :class="{ 'is-hidden': !props.open }">熙烘焙</span>
      </span>
      <span class="app-sidebar__subtitle">新后台 v2</span>
    </div>
    <nav class="app-sidebar__nav">
      <el-tooltip
        v-for="item in ADMIN_NAV_ITEMS"
        :key="item.key"
        :content="item.label"
        placement="right"
        :disabled="open"
        :show-after="200"
      >
        <RouterLink
          :to="item.to"
          class="app-sidebar__link"
          :class="{ 'app-sidebar__link--active': activeKey === item.key }"
        >
          <el-icon class="app-sidebar__link-icon"><component :is="item.icon" /></el-icon>
          <span class="app-sidebar__link-text">{{ item.label }}</span>
        </RouterLink>
      </el-tooltip>
    </nav>
  </aside>
</template>
