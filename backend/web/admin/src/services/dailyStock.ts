import http from "./http";

import type { DailyStockItem, DailyStockListPayload } from "@/types/dailyStock";

interface DailyStockListResponse {
  code: number;
  data: DailyStockListPayload;
}

interface DailyStockItemResponse {
  code: number;
  data: DailyStockItem;
}

export const dailyStockService = {
  async list(date: string): Promise<DailyStockListPayload> {
    const response = await http.get<DailyStockListResponse>("/daily-stock", {
      params: { date },
    });
    return response.data.data;
  },

  async setTotal(productId: string, date: string, totalQty: number): Promise<DailyStockItem> {
    const response = await http.put<DailyStockItemResponse>(`/daily-stock/${productId}`, {
      date,
      totalQty,
    });
    return response.data.data;
  },
};
