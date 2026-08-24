export const ORDER_STATUS_LABELS: Record<string, string> = {
  pending: "待确认",
  confirmed: "已确认",
  making: "制作中",
  delivering: "配送中",
  done: "已完成",
  cancelled: "已取消",
};

export const USER_CANCELABLE_ORDER_STATUSES = ["pending", "confirmed"];

export const ORDER_PROGRESS_STEPS = [
  {
    status: "pending",
    title: "提交订单",
    description: "订单已创建，等待门店确认",
  },
  {
    status: "confirmed",
    title: "门店确认",
    description: "门店已确认商品和取货/配送时间",
  },
  {
    status: "making",
    title: "制作中",
    description: "蛋糕正在制作，请留意后续状态",
  },
  {
    status: "delivering",
    title: "配送/待取",
    description: "订单正在配送或等待到店自提",
  },
  {
    status: "done",
    title: "已完成",
    description: "订单已完成，感谢购买",
  },
];

export const PAYMENT_STATUS_LABELS: Record<string, string> = {
  unpaid: "待支付",
  paid: "已支付",
  expired: "支付超时",
};

export const PAYABLE_PAYMENT_STATUS = "unpaid";

export type OrderListFilterKey = "all" | "unpaid" | "processing" | "done" | "closed";

export interface OrderFilterInput {
  status: string;
  paymentStatus?: string;
}

export type OrderActionInput = OrderFilterInput;

export interface OrderListFilterConfig {
  key: OrderListFilterKey;
  label: string;
  emptyText: string;
  match: (order: OrderFilterInput) => boolean;
}

const PROCESSING_ORDER_STATUSES = ["pending", "confirmed", "making", "delivering"];
const CLOSED_ORDER_STATUSES = ["cancelled"];
const CLOSED_PAYMENT_STATUSES = ["expired"];

function normalizedPaymentStatus(order: OrderFilterInput): string {
  return order.paymentStatus || PAYABLE_PAYMENT_STATUS;
}

function isClosedOrder(order: OrderFilterInput): boolean {
  return CLOSED_ORDER_STATUSES.includes(order.status) || CLOSED_PAYMENT_STATUSES.includes(normalizedPaymentStatus(order));
}

export function canUserCancelOrder(order: OrderActionInput): boolean {
  return USER_CANCELABLE_ORDER_STATUSES.includes(order.status) && !isClosedOrder(order);
}

export function canPayOrder(order: OrderActionInput): boolean {
  return normalizedPaymentStatus(order) === PAYABLE_PAYMENT_STATUS && !isClosedOrder(order);
}

export const DEFAULT_ORDER_LIST_FILTER: OrderListFilterKey = "all";

export const ORDER_LIST_FILTERS: OrderListFilterConfig[] = [
  {
    key: "all",
    label: "全部",
    emptyText: "暂无订单",
    match: () => true,
  },
  {
    key: "unpaid",
    label: "待支付",
    emptyText: "暂无待支付订单",
    match: (order) => normalizedPaymentStatus(order) === PAYABLE_PAYMENT_STATUS && !isClosedOrder(order),
  },
  {
    key: "processing",
    label: "进行中",
    emptyText: "暂无进行中的订单",
    match: (order) => PROCESSING_ORDER_STATUSES.includes(order.status) && !isClosedOrder(order),
  },
  {
    key: "done",
    label: "已完成",
    emptyText: "暂无已完成订单",
    match: (order) => order.status === "done",
  },
  {
    key: "closed",
    label: "已关闭",
    emptyText: "暂无已关闭订单",
    match: isClosedOrder,
  },
];
