import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const decorationPage = readFileSync(
  resolve("src/pages/decoration/DecorationPage.vue"),
  "utf8",
);

const requiredSnippets = [
  "selectedBlock.type === 'categoryGrid'",
  "getStringListProp('categoryIds')",
  "selectedBlock.type === 'quickLinks' || selectedBlock.type === 'serviceGrid'",
  "addLinkItem",
  "removeLinkItem",
  "setItemStringProp(item, 'linkType'",
  "setItemStringProp(item, 'linkTarget'",
  "selectedBlock.type === 'productShelf'",
  "openProductPicker",
  "rememberShelfProducts",
  "getProductDisplayTitle(productId)",
  "selectedBlock.type === 'memberSummary'",
  "getStringProp('cardSubtitle')",
  "getStringProp('cardValidity')",
  "getNumberProp('balanceFen')",
  "getNumberProp('benefitCardCount')",
  "data-testid=\"decoration-page-select\"",
  ":data-testid=\"`decoration-page-tab-${page.value}`\"",
  "data-testid=\"decoration-save-draft\"",
  "data-testid=\"decoration-publish\"",
  ":data-testid=\"`decoration-block-${block.id}`\"",
  "data-testid=\"decoration-selected-products\"",
  "data-testid=\"decoration-open-product-picker\"",
  "data-testid=\"decoration-hero-upload\"",
  "multiple",
  "assetsService.uploadDecorationImage",
  "uploadHeroImages",
  "files = Array.from(input.files ?? [])",
  "getObjectArrayProp(\"items\").push",
  "getItemStringListProp(item, 'badges')",
  "setItemStringListProp(item, 'badges'",
  "data-testid=\"decoration-product-picker-dialog\"",
  "data-testid=\"decoration-product-picker-search\"",
  "data-testid=\"decoration-product-picker-search-button\"",
  "data-testid=\"decoration-product-picker-table\"",
  ":data-testid=\"`decoration-product-picker-add-${getProductIdentity(row)}`\"",
  "selectedBlock.type === 'noticeList'",
];

const missing = requiredSnippets.filter((snippet) => !decorationPage.includes(snippet));

if (missing.length > 0) {
  console.error("Decoration editor structural check failed. Missing snippets:");
  for (const snippet of missing) {
    console.error(`- ${snippet}`);
  }
  process.exit(1);
}

console.log("Decoration editor structural checks passed.");
