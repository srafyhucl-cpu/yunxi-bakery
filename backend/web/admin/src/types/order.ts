export type OrderStatus =
  | "pending"
  | "confirmed"
  | "making"
  | "delivering"
  | "done"
  | "cancelled";

export interface OrderItem {
  product_id: string;
  title: string;
  price_fen: number;
  quantity: number;
}

export interface OrderTimelineEvent {
  id: number;
  status: OrderStatus;
  operator: string;
  note: string;
  createdAt: string;
}

export interface OrderListItem {
  id: string;
  status: OrderStatus;
  paymentStatus: string;
  paymentMethod: string;
  paymentPaidAt: string;
  paymentExpiredAt: string;
  paymentExpiredReason: string;
  totalFen: number;
  createdAt: string;
  updatedAt: string;
  itemTitle: string;
  itemCount: number;
  items: OrderItem[];
  receiverName: string;
  receiverPhone: string;
  deliveryType: string;
  deliveryAddress: string;
  expectTime: string;
  remark: string;
  timeline: OrderTimelineEvent[];
}

export interface OrderListPayload {
  items: OrderListItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface OrderExpireTimeoutPayload {
  expiredCount: number;
  orders: OrderListItem[];
}

export interface OrderSummaryCard {
  key: string;
  label: string;
  description: string;
  count: number;
  totalFen: number;
}

export interface OrderSummaryPayload {
  cards: OrderSummaryCard[];
  totalCount: number;
  totalFen: number;
  keyword: string;
}
