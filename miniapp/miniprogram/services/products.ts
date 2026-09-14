import { request } from "./http";
import { API_BASE_URL, IS_USING_LOCAL_API } from "./config";
import { getProductById, getProductsByIds, listActiveProducts } from "../utils/catalog";
import { createCachedLoader, type CachedLoaderOptions } from "../utils/cache";
import type { CatalogProduct } from "../types/catalog";

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
  meta?: ProductPageMeta;
}

interface ListProductsOptions {
  ids?: string[];
  categoryId?: string;
  featured?: boolean;
  sort?: "popular";
  limit?: number;
  offset?: number;
  keyword?: string;
}

export interface ProductCategory {
  id: string;
  title: string;
  sort: number;
  productCount: number;
}

export interface ProductPageMeta {
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
}

export interface ProductPage {
  items: CatalogProduct[];
  meta: ProductPageMeta;
}

const PRODUCT_CACHE_TTL_MS = 5 * 60 * 1000;

function isWrappedCatalogProducts(value: unknown): value is WrappedApiResponse<CatalogProduct[]> {
  const candidate = value as Partial<WrappedApiResponse<CatalogProduct[]>>;
  return Boolean(candidate && typeof candidate === "object" && Array.isArray(candidate.data));
}

function isWrappedCatalogProduct(value: unknown): value is WrappedApiResponse<CatalogProduct | null> {
  const candidate = value as Partial<WrappedApiResponse<CatalogProduct | null>>;
  return Boolean(candidate && typeof candidate === "object" && "data" in candidate);
}

function isWrappedProductCategories(value: unknown): value is WrappedApiResponse<ProductCategory[]> {
  const candidate = value as Partial<WrappedApiResponse<ProductCategory[]>>;
  return Boolean(candidate && typeof candidate === "object" && Array.isArray(candidate.data));
}

function buildProductsPath(options: ListProductsOptions): string {
  const params: string[] = [];
  if (options.ids?.length) {
    params.push(`ids=${encodeURIComponent(options.ids.join(","))}`);
  }
  if (options.categoryId) {
    params.push(`categoryId=${encodeURIComponent(options.categoryId)}`);
  }
  if (options.featured) {
    params.push("featured=true");
  }
  if (options.sort) {
    params.push(`sort=${encodeURIComponent(options.sort)}`);
  }
  if (options.limit) {
    params.push(`limit=${encodeURIComponent(String(options.limit))}`);
  }
  if (options.offset !== undefined) {
    params.push(`offset=${encodeURIComponent(String(options.offset))}`);
  }
  if (options.keyword) {
    params.push(`keyword=${encodeURIComponent(options.keyword)}`);
  }
  return `/api/v1/miniapp/products${params.length ? `?${params.join("&")}` : ""}`;
}

function normalizeRemoteProducts(products: CatalogProduct[]): CatalogProduct[] {
  return dedupeDisplayProducts(products.map((product) => normalizeRemoteProduct(product)));
}

function normalizeRemoteProduct(product: CatalogProduct): CatalogProduct {
  return {
    ...product,
    imageUrl: normalizeImageUrl(product.imageUrl)
  };
}

function normalizeImageUrl(imageUrl: string): string {
  if (!imageUrl || imageUrl.startsWith("http://") || imageUrl.startsWith("https://")) {
    return imageUrl;
  }
  return `${API_BASE_URL}${imageUrl.startsWith("/") ? "" : "/"}${imageUrl}`;
}

function normalizeDisplayText(value: string): string {
  return value.trim().replace(/\s+/g, "").toLocaleLowerCase();
}

function getDisplayDedupKey(product: CatalogProduct): string {
  const normalizedTitle = normalizeDisplayText(product.title);
  return [
    normalizedTitle,
    product.priceFen
  ].join("|");
}

function dedupeDisplayProducts(products: CatalogProduct[]): CatalogProduct[] {
  const seen = new Set<string>();
  return products.filter((product) => {
    const key = getDisplayDedupKey(product);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function buildProductsCacheKey(options: ListProductsOptions = {}): string {
  return JSON.stringify({
    ids: options.ids ?? [],
    categoryId: options.categoryId ?? "",
    featured: Boolean(options.featured),
    sort: options.sort ?? "",
    // limit 参与缓存键：首页货架(6)/购物车推荐(4)/详情关联(5) 共用 featured 时不得互相复用缓存
    limit: options.limit ?? 0,
    offset: options.offset ?? 0,
    keyword: options.keyword ?? ""
  });
}

function normalizeProductPageMeta(
  meta: ProductPageMeta | undefined,
  options: ListProductsOptions,
  itemCount: number
): ProductPageMeta {
  const fallbackOffset = Math.max(0, options.offset ?? 0);
  const fallbackLimit = Math.max(1, options.limit ?? (itemCount || 1));
  const total = Math.max(0, Number(meta?.total ?? fallbackOffset + itemCount));
  const limit = Math.max(1, Number(meta?.limit ?? fallbackLimit));
  const offset = Math.max(0, Number(meta?.offset ?? fallbackOffset));
  return {
    total,
    limit,
    offset,
    hasMore: typeof meta?.hasMore === "boolean" ? meta.hasMore : offset + itemCount < total
  };
}

async function fetchProducts(options: ListProductsOptions = {}): Promise<CatalogProduct[]> {
  try {
    const response = await request<WrappedApiResponse<CatalogProduct[]>>({
      path: buildProductsPath(options)
    });
    if (isWrappedCatalogProducts(response)) {
      const products = normalizeRemoteProducts(response.data);
      if (products.length > 0 || !IS_USING_LOCAL_API) {
        return products;
      }
    }
  } catch (error) {
    if (!IS_USING_LOCAL_API) {
      throw error;
    }
    // 本地后端调试失败时保留 mock，避免开发页面完全不可用。
  }
  return options.ids?.length ? getProductsByIds(options.ids) : listActiveProducts();
}

const cachedFetchProducts = createCachedLoader(fetchProducts, buildProductsCacheKey);

export async function listProducts(
  options: ListProductsOptions = {},
  cacheOptions: Partial<CachedLoaderOptions> = {}
): Promise<CatalogProduct[]> {
  return cachedFetchProducts(options, {
    ttlMs: PRODUCT_CACHE_TTL_MS,
    ...cacheOptions
  });
}

export async function fetchProductListing(options: ListProductsOptions = {}): Promise<ProductPage> {
  const response = await request<WrappedApiResponse<CatalogProduct[]>>({
    path: buildProductsPath(options)
  });
  if (isWrappedCatalogProducts(response)) {
    const items = normalizeRemoteProducts(response.data);
    return {
      items,
      meta: normalizeProductPageMeta(response.meta, options, items.length)
    };
  }
  throw new Error("商品分页接口响应格式异常");
}

async function fetchProductDetail(productId: string): Promise<CatalogProduct | null> {
  try {
    const response = await request<WrappedApiResponse<CatalogProduct | null>>({
      path: `/api/v1/miniapp/products/${productId}`
    });
    if (isWrappedCatalogProduct(response)) {
      return response.data ? normalizeRemoteProduct(response.data) : null;
    }
  } catch (error) {
    if (!IS_USING_LOCAL_API) {
      throw error;
    }
    // 本地后端调试失败时使用本地详情兜底。
  }
  return getProductById(productId) ?? null;
}

const cachedFetchProductDetail = createCachedLoader(fetchProductDetail, (productId) => productId);

export async function getProductDetail(
  productId: string,
  cacheOptions: Partial<CachedLoaderOptions> = {}
): Promise<CatalogProduct | null> {
  return cachedFetchProductDetail(productId, {
    ttlMs: PRODUCT_CACHE_TTL_MS,
    ...cacheOptions
  });
}

async function fetchProductCategories(): Promise<ProductCategory[]> {
  try {
    const response = await request<WrappedApiResponse<ProductCategory[]>>({
      path: "/api/v1/miniapp/product-categories"
    });
    if (isWrappedProductCategories(response)) {
      return response.data;
    }
  } catch {
    // 分类接口不可用时交给页面基于商品字段兜底聚合。
  }
  return [];
}

const cachedFetchProductCategories = createCachedLoader(fetchProductCategories, () => "product-categories");

export async function listProductCategories(
  cacheOptions: Partial<CachedLoaderOptions> = {}
): Promise<ProductCategory[]> {
  return cachedFetchProductCategories({
    ttlMs: PRODUCT_CACHE_TTL_MS,
    ...cacheOptions
  });
}
