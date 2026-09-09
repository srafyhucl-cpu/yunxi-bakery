import { request } from "./http";

export interface DeliveryQuotePayload {
  requestId: string;
  fulfillmentMethod: "pickup" | "beijing_delivery";
  pickupAddress?: string;
  receiverName?: string;
  receiverPhone?: string;
  receiverAddress?: string;
  expectTime?: string;
  itemCount?: number;
  goodsTotalFen?: number;
  items?: Array<{
    productId: string;
    quantity: number;
  }>;
}

export interface DeliveryQuoteData {
  quoteId?: string;
  status: string;
  deliveryFeeFen?: number | null;
  quoteTotalFen?: number | null;
  expiresAt?: string;
  message?: string;
}

interface DeliveryQuoteApiResponse {
  code: number;
  data: DeliveryQuoteData;
}

/**
 * 请求北京闪送或门店自取报价
 */
export async function requestDeliveryQuote(
  payload: DeliveryQuotePayload
): Promise<DeliveryQuoteData> {
  const res = await request<DeliveryQuoteApiResponse, DeliveryQuotePayload>({
    method: "POST",
    path: "/api/v1/miniapp/delivery/quotes",
    data: payload
  });
  return res.data;
}
