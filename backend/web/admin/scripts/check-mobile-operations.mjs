import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const navigation = readFileSync(resolve("src/constants/adminNavigation.ts"), "utf8");
const bottomNav = readFileSync(resolve("src/components/layout/BottomNav.vue"), "utf8");
const appSidebar = readFileSync(resolve("src/components/layout/AppSidebar.vue"), "utf8");
const overviewPage = readFileSync(resolve("src/pages/overview/OverviewPage.vue"), "utf8");

const requiredSnippets = [
  [navigation, "ADMIN_NAV_ITEMS"],
  [navigation, "MOBILE_ADMIN_NAV_ITEMS"],
  [navigation, "mobilePrimary: true"],
  [navigation, "key: \"orders\""],
  [navigation, "key: \"transfers\""],
  [navigation, "key: \"settings\""],
  [bottomNav, "MOBILE_ADMIN_NAV_ITEMS"],
  [bottomNav, ":data-testid=\"`bottom-nav-${item.key}`\""],
  [bottomNav, "item.shortLabel"],
  [appSidebar, "ADMIN_NAV_ITEMS"],
  [overviewPage, "data-testid=\"overview-mobile-ops\""],
  [overviewPage, "mobileOperationLinks"],
  [overviewPage, "/orders?status=pending"],
  [overviewPage, "/transfers"],
  [overviewPage, "/settings/shop"],
];

const missing = requiredSnippets
  .filter(([content, snippet]) => !content.includes(snippet))
  .map(([, snippet]) => snippet);

if (missing.length > 0) {
  console.error("Mobile operations structural check failed. Missing snippets:");
  for (const snippet of missing) {
    console.error(`- ${snippet}`);
  }
  process.exit(1);
}

console.log("Mobile operations structural checks passed.");
