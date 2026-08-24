import type { OrderStatus } from "@/types/order";

export const ORDER_STATUS_OPTIONS: Array<{
  value: OrderStatus;
  label: string;
  tagType: "success" | "warning" | "info" | "danger" | "primary";
}> = [
  { value: "pending", label: "待确认", tagType: "warning" },
  { value: "confirmed", label: "已确认", tagType: "danger" },
  { value: "making", label: "制作中", tagType: "danger" },
  { value: "delivering", label: "配送中", tagType: "primary" },
  { value: "done", label: "已完成", tagType: "success" },
  { value: "cancelled", label: "已取消", tagType: "info" },
];

export const ORDER_STATUS_ACTIONS: Record<
  OrderStatus,
  Array<{ status: OrderStatus; label: string; type: "primary" | "success" | "warning" | "danger" }>
> = {
  pending: [
    { status: "confirmed", label: "确认订单", type: "primary" },
    { status: "cancelled", label: "取消", type: "danger" },
  ],
  confirmed: [
    { status: "making", label: "开始制作", type: "primary" },
    { status: "cancelled", label: "取消", type: "danger" },
  ],
  making: [
    { status: "delivering", label: "配送中", type: "primary" },
    { status: "done", label: "完成自提", type: "success" },
  ],
  delivering: [{ status: "done", label: "完成", type: "success" }],
  done: [],
  cancelled: [],
};

export type OrderBoardFilterKey = "all" | "unpaid" | "pending" | "fulfilling" | "done" | "closed";

export interface OrderBoardFilterInput {
  status: OrderStatus;
  paymentStatus: string;
}

export interface OrderBoardFilterConfig {
  key: OrderBoardFilterKey;
  label: string;
  description: string;
  statusValue: OrderStatus | "";
  match: (order: OrderBoardFilterInput) => boolean;
}

const FULFILLING_ORDER_STATUSES: OrderStatus[] = ["confirmed", "making", "delivering"];

export const ORDER_BOARD_FILTERS: OrderBoardFilterConfig[] = [
  {
    key: "all",
    label: "全部订单",
    description: "当前筛选范围",
    statusValue: "",
    match: () => true,
  },
  {
    key: "unpaid",
    label: "待支付",
    description: "需要跟进付款",
    statusValue: "",
    match: (order) => order.paymentStatus === "unpaid" && order.status !== "cancelled",
  },
  {
    key: "pending",
    label: "待确认",
    description: "新订单待接单",
    statusValue: "pending",
    match: (order) => order.status === "pending",
  },
  {
    key: "fulfilling",
    label: "履约中",
    description: "确认/制作/配送",
    statusValue: "confirmed",
    match: (order) => FULFILLING_ORDER_STATUSES.includes(order.status),
  },
  {
    key: "done",
    label: "已完成",
    description: "已交付订单",
    statusValue: "done",
    match: (order) => order.status === "done",
  },
  {
    key: "closed",
    label: "已关闭",
    description: "取消或支付超时",
    statusValue: "cancelled",
    match: (order) => order.status === "cancelled" || order.paymentStatus === "expired",
  },
];

export function orderStatusLabel(status: string): string {
  return ORDER_STATUS_OPTIONS.find((item) => item.value === status)?.label || status || "未知";
}

export function orderStatusTagType(
  status: string,
): "success" | "warning" | "info" | "danger" | "primary" {
  return ORDER_STATUS_OPTIONS.find((item) => item.value === status)?.tagType || "info";
}
