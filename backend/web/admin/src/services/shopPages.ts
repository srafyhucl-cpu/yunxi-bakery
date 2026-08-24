import http from "./http";

import type { ShopPageAdminPayload, ShopPageConfig } from "@/types/shopPage";

interface ApiResponse<T> {
  code: number;
  data: T;
}

export const shopPagesService = {
  async getPage(pageId: string): Promise<ShopPageAdminPayload> {
    const response = await http.get<ApiResponse<ShopPageAdminPayload>>(
      `/shop-config/pages/${pageId}`,
    );
    return response.data.data;
  },

  async saveDraft(pageId: string, pageConfig: ShopPageConfig): Promise<ShopPageConfig> {
    const response = await http.put<ApiResponse<ShopPageConfig>>(
      `/shop-config/pages/${pageId}/draft`,
      pageConfig,
    );
    return response.data.data;
  },

  async publish(pageId: string): Promise<ShopPageConfig> {
    const response = await http.post<ApiResponse<ShopPageConfig>>(
      `/shop-config/pages/${pageId}/publish`,
    );
    return response.data.data;
  },
};

