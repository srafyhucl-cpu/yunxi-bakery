import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const addressesPage = readFileSync(resolve("src/pages/addresses/AddressesPage.vue"), "utf8");
const routes = readFileSync(resolve("src/router/routes.ts"), "utf8");
const navigation = readFileSync(resolve("src/constants/adminNavigation.ts"), "utf8");

const requiredPageSnippets = [
  "data-testid=\"addresses-page\"",
  "data-testid=\"addresses-search-input\"",
  "data-testid=\"addresses-search-submit\"",
  "data-testid=\"addresses-reset-filters\"",
  "data-testid=\"addresses-refresh\"",
  "data-testid=\"addresses-create\"",
  "data-testid=\"addresses-table\"",
  ":data-testid=\"`addresses-open-detail-${row.id}`\"",
  ":data-testid=\"`addresses-edit-${row.id}`\"",
  ":data-testid=\"`addresses-set-default-${row.id}`\"",
  ":data-testid=\"`addresses-delete-${row.id}`\"",
  "data-testid=\"addresses-detail-drawer\"",
  ":data-testid=\"`addresses-detail-edit-${selectedAddress.id}`\"",
  "data-testid=\"addresses-audit-section\"",
  "data-testid=\"addresses-form-drawer\"",
  "data-testid=\"addresses-form-user-id\"",
  "data-testid=\"addresses-form-receiver-name\"",
  "data-testid=\"addresses-form-receiver-phone\"",
  "data-testid=\"addresses-form-address\"",
  "data-testid=\"addresses-form-default\"",
  "data-testid=\"addresses-form-submit\"",
  "addressesService.listAddresses",
  "addressesService.saveAddress",
  "addressesService.setDefault",
  "addressesService.deleteAddress",
  "auditLogs.length",
];

const requiredRouteSnippets = [
  "path: \"/addresses\"",
  "name: \"addresses\"",
  "navKey: \"addresses\"",
  "@/pages/addresses/AddressesPage.vue",
];

const requiredSidebarSnippets = [
  "label: \"顾客地址\"",
  "to: \"/addresses\"",
  "key: \"addresses\"",
];

const missing = [
  ...requiredPageSnippets.filter((snippet) => !addressesPage.includes(snippet)),
  ...requiredRouteSnippets.filter((snippet) => !routes.includes(snippet)),
  ...requiredSidebarSnippets.filter((snippet) => !navigation.includes(snippet)),
];

if (missing.length > 0) {
  console.error("Addresses page structural check failed. Missing snippets:");
  for (const snippet of missing) {
    console.error(`- ${snippet}`);
  }
  process.exit(1);
}

console.log("Addresses page structural checks passed.");
