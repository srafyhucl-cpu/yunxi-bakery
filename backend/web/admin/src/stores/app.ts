import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { useDevice } from "@/composables/useDevice";

export const useAppStore = defineStore("app", () => {
  const sidebarOpen = ref(true);
  const globalLoading = ref(false);
  const { deviceType, isPhone, isPad, isPC } = useDevice();

  const shouldShowSidebar = computed(() => !isPhone.value);

  function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value;
  }

  return {
    sidebarOpen,
    globalLoading,
    deviceType,
    isPhone,
    isPad,
    isPC,
    shouldShowSidebar,
    toggleSidebar,
  };
});
