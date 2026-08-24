<script setup lang="ts">
import { useRoute } from "vue-router";

import { MOBILE_ADMIN_NAV_ITEMS } from "@/constants/adminNavigation";

const route = useRoute();
</script>

<template>
  <nav class="bottom-nav">
    <RouterLink
      v-for="item in MOBILE_ADMIN_NAV_ITEMS"
      :key="item.key"
      :to="item.to"
      class="bottom-nav__item"
      :class="{ 'bottom-nav__item--active': route.meta.navKey === item.key }"
      :data-testid="`bottom-nav-${item.key}`"
    >
      <el-icon class="bottom-nav__icon"><component :is="item.icon" /></el-icon>
      <span>{{ item.shortLabel }}</span>
    </RouterLink>
  </nav>
</template>
