import { request } from "./http";

export interface CreateOrderPayload {
  items: Array<{
    productId: string;
    quantity: number;
    title?: string;
    priceFen?: number;
  }>;
  receiverName: string;
  receiverPhone: string;
  deliveryType: "pickup" | "delivery";
  deliveryAddress: string;
  expectTime: string;
  remark: string;
}

export interface OrderSummary {
  id: string;
  status: string;
  paymentStatus?: string;
  paymentMethod?: string;
  paymentPaidAt?: string;
  paymentExpiredAt?: string;
  paymentExpiredReason?: string;
  totalFen: number;
  createdAt: string;
  updatedAt?: string;
  itemTitle: string;
  itemCount?: number;
  items?: Array<{
    product_id: string;
    title: string;
    price_fen: number;
    quantity: number;
  }>;
  receiverName?: string;
  receiverPhone?: string;
  deliveryType?: string;
  deliveryAddress?: string;
  expectTime?: string;
  remark?: string;
  timeline?: Array<{
    id: number;
    status: string;
    operator: string;
    note: string;
    createdAt: string;
  }>;
}

export interface WechatPaymentParams {
  timeStamp: string;
  nonceStr: string;
  package: string;
  signType: "RSA" | "MD5" | "HMAC-SHA256";
  paySign: string;
}

export interface PreparedPayment {
  mode: "wechat" | "mock";
  orderId: string;
  paymentMethod: "wechat" | "mock";
  paymentStatus: string;
  paymentParams: Partial<WechatPaymentParams> & {
    action?: string;
    message?: string;
  };
}

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

function unwrapResponse<TData>(response: WrappedApiResponse<TData> | TData): TData {
  if (response && typeof response === "object" && "data" in response) {
    return (response as WrappedApiResponse<TData>).data;
  }
  return response as TData;
}

export async function createOrder(payload: CreateOrderPayload): Promise<{ orderId: string }> {
  const response = await request<WrappedApiResponse<{ orderId: string }>, CreateOrderPayload>({
    method: "POST",
    path: "/api/v1/miniapp/orders",
    data: payload
  });
  return unwrapResponse(response);
}

export async function listOrders(): Promise<OrderSummary[]> {
  const response = await request<WrappedApiResponse<OrderSummary[]> | OrderSummary[]>({
    path: "/api/v1/miniapp/orders"
  });
  return unwrapResponse(response);
}

export async function getOrder(orderId: string): Promise<OrderSummary> {
  const response = await request<WrappedApiResponse<OrderSummary>>({
    path: `/api/v1/miniapp/orders/${orderId}`
  });
  return unwrapResponse(response);
}

export async function cancelOrder(orderId: string): Promise<OrderSummary> {
  const response = await request<WrappedApiResponse<OrderSummary>>({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/cancel`
  });
  return unwrapResponse(response);
}

export async function mockPayOrder(orderId: string): Promise<OrderSummary> {
  const response = await request<WrappedApiResponse<OrderSummary>>({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/mock-pay`
  });
  return unwrapResponse(response);
}

export async function prepareOrderPayment(orderId: string): Promise<PreparedPayment> {
  const response = await request<WrappedApiResponse<PreparedPayment>>({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/prepare-payment`
  });
  return unwrapResponse(response);
}

export async function payWithBalance(orderId: string): Promise<OrderSummary> {
  const response = await request<
    WrappedApiResponse<OrderSummary> | OrderSummary,
    Record<string, never>
  >({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/pay-with-balance`
  });
  return unwrapResponse(response);
}

export async function prepareCombinedPayment(
  orderId: string,
  balanceFen: number
): Promise<PreparedPayment> {
  const response = await request<
    WrappedApiResponse<PreparedPayment> | PreparedPayment,
    { balanceFen: number }
  >({
    method: "POST",
    path: `/api/v1/miniapp/orders/${orderId}/prepare-combined-payment`,
    data: { balanceFen }
  });
  return unwrapResponse(response);
}
