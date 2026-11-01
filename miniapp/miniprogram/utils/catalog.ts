import { CATALOG_PRODUCTS } from "../config/mock-catalog";
import type { CatalogProduct } from "../types/catalog";

export function listActiveProducts(): CatalogProduct[] {
  return CATALOG_PRODUCTS.filter((product) => product.isActive);
}

export function getProductById(productId: string): CatalogProduct | undefined {
  return CATALOG_PRODUCTS.find((product) => product.id === productId);
}

export function getProductsByIds(productIds: string[]): CatalogProduct[] {
  const byId = new Map(CATALOG_PRODUCTS.map((product) => [product.id, product]));
  return productIds
    .map((productId) => byId.get(productId))
    .filter((product): product is CatalogProduct => Boolean(product));
}

