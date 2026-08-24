/** 会员资产纯函数工具：券分类 / 积分来源文案 / 支付分支 / 充值金额校验。 */

export const MIN_RECHARGE_FEN = 100;
export const MAX_RECHARGE_FEN = 50000;

export interface MemberCoupon {
  couponId: string;
  templateId: string;
  title: string;
  status: string;
  valueFen: number;
  thresholdFen: number;
  deductedFen: number;
  validFrom: string;
  validUntil: string;
  orderNo: string;
}

export type CouponTab = "available" | "used" | "refunded" | "expired";

export interface CouponView {
  tab: CouponTab;
  note: string;
}

export interface PointsLedgerItem {
  amount: number;
  total: number;
  event_type: string;
  source: string;
  biz_type: string;
  occurred_at: string;
}

export type PaymentBranch = "free" | "balance" | "combined" | "online";

function dateString(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function classifyCouponStatus(coupon: MemberCoupon, now: Date = new Date()): CouponView {
  const today = dateString(now);
  if (coupon.status === "CONSUME") {
    return { tab: "used", note: "已使用" };
  }
  if (coupon.status === "BACK") {
    return { tab: "refunded", note: "已退回" };
  }
  if (coupon.status === "TAKE") {
    if (coupon.validUntil && coupon.validUntil < today) {
      return { tab: "expired", note: "已过期" };
    }
    if (coupon.validFrom && coupon.validFrom > today) {
      return { tab: "expired", note: "未生效" };
    }
    return { tab: "available", note: "未使用" };
  }
  return { tab: "expired", note: "已过期" };
}

export function mapPointsSourceLabel(item: PointsLedgerItem): string {
  const biz = item.biz_type || item.event_type || "";
  if (biz === "order_award") {
    return "订单奖励";
  }
  if (biz === "order_redeem") {
    return "订单抵扣";
  }
  if (biz === "order_refund") {
    return "退款退回";
  }
  const source = item.source || "";
  if (source === "webhook") {
    return "有赞同步";
  }
  if (source === "import") {
    return "导入";
  }
  if (source === "order") {
    return "订单消费";
  }
  return "积分变动";
}

export function buildPaymentBranch(params: {
  remainFen: number;
  balanceFen: number;
  balanceEnabled: boolean;
}): PaymentBranch {
  const { remainFen, balanceFen, balanceEnabled } = params;
  if (remainFen <= 0) {
    return "free";
  }
  if (balanceEnabled && balanceFen >= remainFen) {
    return "balance";
  }
  if (balanceEnabled && balanceFen > 0) {
    return "combined";
  }
  return "online";
}

export function isValidRechargeAmount(amountFen: number): boolean {
  return (
    Number.isInteger(amountFen) &&
    amountFen >= MIN_RECHARGE_FEN &&
    amountFen <= MAX_RECHARGE_FEN
  );
}