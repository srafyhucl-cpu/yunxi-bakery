export const PAYMENT_STATUS_OPTIONS: Array<{
  value: string;
  label: string;
  tagType: "success" | "warning" | "info" | "danger" | "primary";
}> = [
  { value: "unpaid", label: "待支付", tagType: "warning" },
  { value: "paid", label: "已支付", tagType: "success" },
  { value: "expired", label: "支付超时", tagType: "info" },
];

export function paymentStatusLabel(status: string): string {
  return PAYMENT_STATUS_OPTIONS.find((item) => item.value === status)?.label || status || "待支付";
}

export function paymentStatusTagType(
  status: string,
): "success" | "warning" | "info" | "danger" | "primary" {
  return PAYMENT_STATUS_OPTIONS.find((item) => item.value === status)?.tagType || "info";
}
