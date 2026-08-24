import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const shopSettingsPage = readFileSync(resolve("src/pages/settings/ShopSettingsPage.vue"), "utf8");

const requiredSnippets = [
  "data-testid=\"shop-settings-page\"",
  "data-testid=\"shop-settings-reset\"",
  "data-testid=\"shop-settings-refresh\"",
  "data-testid=\"shop-settings-save\"",
  "data-testid=\"shop-settings-shop-name\"",
  "data-testid=\"shop-settings-customer-phone\"",
  "data-testid=\"shop-settings-customer-wechat\"",
  "data-testid=\"shop-settings-business-hours\"",
  "data-testid=\"shop-settings-business-hours-tip\"",
  "data-testid=\"shop-settings-business-hours-error\"",
  "data-testid=\"shop-settings-pickup-address\"",
  "data-testid=\"shop-settings-delivery-notice\"",
  "data-testid=\"shop-settings-pickup-notice\"",
  "data-testid=\"shop-settings-privacy-title\"",
  "data-testid=\"shop-settings-privacy-content\"",
  "data-testid=\"shop-settings-agreement-title\"",
  "data-testid=\"shop-settings-agreement-content\"",
  "data-testid=\"shop-settings-after-sales-title\"",
  "data-testid=\"shop-settings-after-sales-content\"",
];

const missing = requiredSnippets.filter((snippet) => !shopSettingsPage.includes(snippet));

if (missing.length > 0) {
  console.error("Shop settings page structural check failed. Missing snippets:");
  for (const snippet of missing) {
    console.error(`- ${snippet}`);
  }
  process.exit(1);
}

console.log("Shop settings page structural checks passed.");
