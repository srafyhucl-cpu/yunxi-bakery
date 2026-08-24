import { defineStore } from "pinia";
import { ref } from "vue";

export interface AdminSettingsSnapshot {
  shopName: string;
  channelCount: number;
}

export const useSettingsStore = defineStore("settings", () => {
  const snapshot = ref<AdminSettingsSnapshot | null>(null);

  function setSnapshot(value: AdminSettingsSnapshot | null) {
    snapshot.value = value;
  }

  return {
    snapshot,
    setSnapshot,
  };
});
