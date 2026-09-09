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
