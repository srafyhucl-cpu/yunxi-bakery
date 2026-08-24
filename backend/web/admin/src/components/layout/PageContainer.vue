<script setup lang="ts">
defineProps<{ noPadding?: boolean }>();
</script>

<template>
  <main class="page-container" :class="{ 'page-container--no-padding': noPadding }">
    <slot />
  </main>
</template>
