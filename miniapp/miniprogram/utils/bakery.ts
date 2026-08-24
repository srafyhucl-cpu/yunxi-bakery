import type { CatalogProduct } from "../types/catalog";

const BAKERY_PATTERNS = ["cake-pink", "cake-cream", "cake-choco", "cake-yellow"] as const;

export function getBakeryPattern(indexOrSeed: number | string): typeof BAKERY_PATTERNS[number] {
  const seed = typeof indexOrSeed === "number"
    ? indexOrSeed
    : indexOrSeed.split("").reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return BAKERY_PATTERNS[Math.abs(seed) % BAKERY_PATTERNS.length];
}

export function getProductImageClass(product: CatalogProduct, index = 0): string {
  if (product.imageUrl) {
    return "";
  }
  const token = `${product.id}-${index}-${product.categoryId}`;
  return getBakeryPattern(token);
}
