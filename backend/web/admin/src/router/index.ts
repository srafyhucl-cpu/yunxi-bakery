import { createRouter, createWebHistory } from "vue-router";
import { createPinia } from "pinia";

import { useAuthStore } from "@/stores/auth";
import { routes } from "./routes";

const pinia = createPinia();

const router = createRouter({
  history: createWebHistory(import.meta.env.VITE_ROUTER_BASE),
  routes,
  scrollBehavior() {
    return { top: 0 };
  },
});

router.beforeEach(async (to) => {
  const authStore = useAuthStore(pinia);
  const isLoginPage = to.name === "login";

  if (!authStore.initialized) {
    try {
      await authStore.fetchProfile();
    } catch {
      authStore.clearProfile();
    }
  }

  if (isLoginPage && authStore.isLoggedIn) {
    return "/ai-dialog";
  }

  if (!isLoginPage && !authStore.isLoggedIn) {
    return {
      name: "login",
      query: { redirect: to.fullPath },
    };
  }

  return true;
});

export default router;
export { pinia };
