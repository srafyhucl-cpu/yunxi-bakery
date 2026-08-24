import { MOCK_PAGE_CONFIGS } from "../config/mock-pages";
import type { PageBlock, PageId, ShopPageConfig } from "../types/page-config";

export function getMockPageConfig(pageId: PageId): ShopPageConfig {
  return MOCK_PAGE_CONFIGS[pageId];
}

export function getEnabledBlocks(config: ShopPageConfig): PageBlock[] {
  return config.blocks.filter((block) => block.enabled);
}

