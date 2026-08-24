import { request } from "./http";
import { createCachedLoader, type CachedLoaderOptions } from "../utils/cache";
import { getMockPageConfig } from "../utils/page-config";
import type { PageId, ShopPageConfig } from "../types/page-config";

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

function isWrappedPageConfig(value: unknown): value is WrappedApiResponse<ShopPageConfig> {
  const candidate = value as Partial<WrappedApiResponse<ShopPageConfig>>;
  return Boolean(candidate && typeof candidate === "object" && candidate.data);
}

const PAGE_CONFIG_CACHE_TTL_MS = 5 * 60 * 1000;

async function fetchPublishedPageConfig(pageId: PageId): Promise<ShopPageConfig> {
  try {
    const response = await request<WrappedApiResponse<ShopPageConfig>>({
      path: `/api/v1/miniapp/pages/${pageId}`
    });
    if (isWrappedPageConfig(response)) {
      return response.data;
    }
  } catch {
    // 后台装修 API 不可用时使用本地 mock，保证小程序 MVP 仍可运行。
  }
  return getMockPageConfig(pageId);
}

const cachedFetchPublishedPageConfig = createCachedLoader(fetchPublishedPageConfig, (pageId) => pageId);

export async function getPublishedPageConfig(
  pageId: PageId,
  cacheOptions: Partial<CachedLoaderOptions> = {}
): Promise<ShopPageConfig> {
  return cachedFetchPublishedPageConfig(pageId, {
    ttlMs: PAGE_CONFIG_CACHE_TTL_MS,
    ...cacheOptions
  });
}
