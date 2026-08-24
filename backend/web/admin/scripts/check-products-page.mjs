import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const productsPage = readFileSync(resolve("src/pages/products/ProductsPage.vue"), "utf8");

const requiredSnippets = [
  "data-testid=\"products-page\"",
  "data-testid=\"products-filter-all\"",
  "data-testid=\"products-filter-active\"",
  "data-testid=\"products-filter-inactive\"",
  "data-testid=\"products-search-input\"",
  "data-testid=\"products-search-submit\"",
  "data-testid=\"products-reset-filters\"",
  "data-testid=\"products-table\"",
  ":data-testid=\"`products-row-title-${row.youzanItemId || row.id}`\"",
  ":data-testid=\"`products-toggle-active-${row.youzanItemId || row.id}`\"",
];

const missing = requiredSnippets.filter((snippet) => !productsPage.includes(snippet));

if (missing.length > 0) {
  console.error("Products page structural check failed. Missing snippets:");
  for (const snippet of missing) {
    console.error(`- ${snippet}`);
  }
  process.exit(1);
}

console.log("Products page structural checks passed.");
