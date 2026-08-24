import http from "./http";

import type {
  OrderExpireTimeoutPayload,
  OrderListItem,
  OrderListPayload,
  OrderSummaryPayload,
  OrderStatus,
} from "@/types/order";

interface OrderListResponse {
  code: number;
  data: OrderListPayload;
}

interface OrderResponse {
  code: number;
  data: OrderListItem;
}

interface OrderExpireTimeoutResponse {
  code: number;
  data: OrderExpireTimeoutPayload;
}

interface OrderSummaryResponse {
  code: number;
  data: OrderSummaryPayload;
}

export const ordersService = {
  async listOrders(
    page: number,
    keyword: string = "",
    status: string = "",
    boardFilter: string = "",
  ): Promise<OrderListPayload> {
    const response = await http.get<OrderListResponse>("/orders", {
      params: {
        page,
        keyword: keyword || undefined,
        status: status || undefined,
        boardFilter: boardFilter || undefined,
      },
    });
    return response.data.data;
  },

  async getSummary(keyword: string = ""): Promise<OrderSummaryPayload> {
    const response = await http.get<OrderSummaryResponse>("/orders/summary", {
      params: {
        keyword: keyword || undefined,
      },
    });
    return response.data.data;
  },

  async getOrder(orderId: string): Promise<OrderListItem> {
    const response = await http.get<OrderResponse>(`/orders/${orderId}`);
    return response.data.data;
  },

  async updateStatus(orderId: string, status: OrderStatus): Promise<OrderListItem> {
    const response = await http.post<OrderResponse>(`/orders/${orderId}/status`, { status });
    return response.data.data;
  },

  async expireUnpaid(orderId: string): Promise<OrderListItem> {
    const response = await http.post<OrderResponse>(`/orders/${orderId}/expire-unpaid`);
    return response.data.data;
  },

  async expireTimeoutUnpaid(): Promise<OrderExpireTimeoutPayload> {
    const response = await http.post<OrderExpireTimeoutResponse>("/orders/expire-timeout-unpaid");
    return response.data.data;
  },
};
