import { TAB_BAR_ITEMS } from "../constants/tab-bar";

interface CustomTabBarInstance {
  data?: {
    selected?: number;
  };
  setData(data: { selected: number }): void;
}

interface PageWithCustomTabBar {
  getTabBar?: () => CustomTabBarInstance;
}

export function syncCustomTabBar(route: string): void {
  const currentPath = route.startsWith("/") ? route : `/${route}`;
  const selected = TAB_BAR_ITEMS.findIndex((item) => item.pagePath === currentPath);
  const pages = getCurrentPages();
  const page = pages[pages.length - 1] as unknown as PageWithCustomTabBar;
  const tabBar = page?.getTabBar?.();
  if (tabBar && selected >= 0 && tabBar.data?.selected !== selected) {
    tabBar.setData({ selected });
  }
}
