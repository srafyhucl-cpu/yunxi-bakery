import { CATALOG_CATEGORIES, CATALOG_PRODUCTS } from "../config/mock-catalog";
import type { CatalogCategory, CatalogProduct } from "../types/catalog";

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

export function getCategoryById(categoryId: string): CatalogCategory | undefined {
  return CATALOG_CATEGORIES.find((category) => category.id === categoryId);
}

export function getCategoriesByIds(categoryIds: string[]): CatalogCategory[] {
  const byId = new Map(CATALOG_CATEGORIES.map((category) => [category.id, category]));
  return categoryIds
    .map((categoryId) => byId.get(categoryId))
    .filter((category): category is CatalogCategory => Boolean(category));
}

