type OrderFulfillmentMethod = "pickup" | "beijing_delivery";

export interface OrderAmountSnapshot {
  totalFen: number;
  goodsTotalFen?: number;
  deliveryFeeFen?: number | null;
  payableFen?: number | null;
  deliveryType?: string;
  fulfillmentMethod?: OrderFulfillmentMethod;
}

export interface OrderAmountView {
  goodsTotalText: string;
  deliveryFeeText: string;
  payableText: string;
  totalText: string;
  deliveryTypeText: string;
  hasDeliveryFee: boolean;
  deliveryFeePending: boolean;
}

export function isBeijingDelivery(order: Pick<OrderAmountSnapshot, "deliveryType" | "fulfillmentMethod">): boolean {
  return order.fulfillmentMethod === "beijing_delivery" || order.deliveryType === "delivery" || order.deliveryType === "beijing_delivery";
}

function formatAmountFen(priceFen: number): string {
  return "¥" + (priceFen / 100).toFixed(2);
}

export function buildOrderAmountView(order: OrderAmountSnapshot): OrderAmountView {
  const beijingDelivery = isBeijingDelivery(order);
  const goodsTotalFen = order.goodsTotalFen ?? order.totalFen;
  const deliveryFeeKnown = typeof order.deliveryFeeFen === "number";
  const deliveryFeeFen = deliveryFeeKnown ? order.deliveryFeeFen ?? 0 : 0;
  const deliveryFeePending = beijingDelivery && !deliveryFeeKnown;
  const payableFen = typeof order.payableFen === "number" ? order.payableFen : order.totalFen;

  return {
    goodsTotalText: formatAmountFen(goodsTotalFen),
    deliveryFeeText: deliveryFeePending ? "待确认" : formatAmountFen(deliveryFeeFen),
    payableText: formatAmountFen(payableFen),
    totalText: formatAmountFen(payableFen),
    deliveryTypeText: beijingDelivery ? "北京闪送" : "到店自提",
    hasDeliveryFee: beijingDelivery,
    deliveryFeePending,
  };
}

export function maskReceiverPhone(phone?: string): string {
  const normalized = (phone || "").trim();
  if (/^\d{11}$/.test(normalized)) {
    return `${normalized.slice(0, 3)}****${normalized.slice(-4)}`;
  }
  if (!normalized) {
    return "手机号待确认";
  }
  if (normalized.length <= 7) {
    return normalized;
  }
  return `${normalized.slice(0, 3)}****${normalized.slice(-4)}`;
}

export function formatOrderDisplayId(orderId: string): string {
  const normalized = orderId.trim();
  if (!normalized) {
    return "待同步";
  }
  const parts = normalized.split("_").filter(Boolean);
  const datePart = parts.find((part) => /^\d{8}$/.test(part));
  const suffix = parts.length > 1 ? parts[parts.length - 1] : "";
  if (datePart && suffix && suffix !== datePart) {
    const dateText = `${datePart.slice(0, 4)}-${datePart.slice(4, 6)}-${datePart.slice(6, 8)}`;
    return `${dateText} · ${suffix.slice(-8).toUpperCase()}`;
  }
  if (normalized.length > 18) {
    return `${normalized.slice(0, 8)}…${normalized.slice(-8)}`;
  }
  return normalized;
}
