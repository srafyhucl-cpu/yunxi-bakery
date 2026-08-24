import http from "./http";

import type { ProductListItem, ProductListPayload } from "@/types/product";

interface ProductListResponse {
  code: number;
  total: number;
  total_active: number;
  total_inactive: number;
  page?: number;
  page_size?: number;
  data: Array<{
    id: number;
    category: string;
    content_type?: string;
    title: string;
    content: string;
    keywords?: string;
    priority: number;
    is_active: boolean;
    youzan_item_id?: string | null;
    item_no?: string | null;
    price_fen?: number | null;
    stock?: number | null;
    sold_num?: number;
    last_sync_source?: string;
    last_sync_ref?: string;
    vector_sync_status?: string;
    updated_at?: string;
  }>;
}

interface ToggleProductResponse {
  code: number;
  is_active: boolean;
  title: string;
}

export interface ReconcileResult {
  checked: number;
  onsale_from_youzan: number;
  deactivated: number;
  deactivated_ids: number[];
  errors: string[];
  duration_ms: number;
}

function normalizeProduct(item: ProductListResponse["data"][number]): ProductListItem {
  return {
    id: item.id,
    category: item.category,
    contentType: item.content_type || "product",
    title: item.title,
    content: item.content,
    keywords: item.keywords || "",
    priority: item.priority,
    isActive: item.is_active,
    youzanItemId: item.youzan_item_id || "",
    itemNo: item.item_no || "",
    priceFen: item.price_fen ?? null,
    stock: item.stock ?? null,
    soldNum: item.sold_num ?? 0,
    lastSyncSource: item.last_sync_source || "",
    lastSyncRef: item.last_sync_ref || "",
    vectorSyncStatus: item.vector_sync_status || "",
    updatedAt: item.updated_at || "",
  };
}

export const productsService = {
  async listProducts(
    page: number,
    keyword: string,
    isActive: string = "",
    syncSource: string = "",
    syncStatus: string = "",
    featuredOnly: boolean = false,
    itemNo: string = "",
    keywordFilter: string = "",
    sortBy: string = "",
    sortOrder: string = "",
  ): Promise<ProductListPayload> {
    const response = await http.get<ProductListResponse>("/products", {
      params: {
        page,
        search: keyword,
        is_active: isActive,
        sync_source: syncSource,
        vector_sync_status: syncStatus,
        featured_only: featuredOnly || undefined,
        item_no: itemNo || undefined,
        keyword_filter: keywordFilter || undefined,
        sort_by: sortBy || undefined,
        sort_order: sortOrder || undefined,
      },
    });
    return {
      items: response.data.data.map(normalizeProduct),
      total: response.data.total,
      totalActive: response.data.total_active ?? 0,
      totalInactive: response.data.total_inactive ?? 0,
      page: response.data.page || page,
      pageSize: response.data.page_size || 30,
    };
  },

  async toggleProductActive(productId: number): Promise<ToggleProductResponse> {
    const response = await http.post<ToggleProductResponse>(`/products/${productId}/toggle-active`);
    return response.data;
  },

  async reconcileProducts(): Promise<ReconcileResult> {
    const response = await http.post<{ code: number; data: ReconcileResult }>("/products/reconcile");
    return response.data.data;
  },
};
