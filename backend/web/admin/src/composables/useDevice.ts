import { computed, onBeforeUnmount, onMounted, ref } from "vue";

export type DeviceType = "phone" | "pad" | "pc";

const width = ref(typeof window === "undefined" ? 1440 : window.innerWidth);

function resolveDeviceType(currentWidth: number): DeviceType {
  if (currentWidth < 768) {
    return "phone";
  }
  if (currentWidth < 1200) {
    return "pad";
  }
  return "pc";
}

export function useDevice() {
  function syncWidth() {
    width.value = window.innerWidth;
  }

  onMounted(() => {
    syncWidth();
    window.addEventListener("resize", syncWidth);
  });

  onBeforeUnmount(() => {
    window.removeEventListener("resize", syncWidth);
  });

  const deviceType = computed(() => resolveDeviceType(width.value));

  return {
    width,
    deviceType,
    isPhone: computed(() => deviceType.value === "phone"),
    isPad: computed(() => deviceType.value === "pad"),
    isPC: computed(() => deviceType.value === "pc"),
  };
}
