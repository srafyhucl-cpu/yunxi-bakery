import { test } from "node:test";
import assert from "node:assert/strict";
import {
  classifyCouponStatus,
  mapPointsSourceLabel,
  buildPaymentBranch,
  isValidRechargeAmount,
  MIN_RECHARGE_FEN,
  MAX_RECHARGE_FEN,
  type MemberCoupon,
} from "../../miniprogram/utils/member-assets.ts";

const NOW = new Date("2026-08-14T12:00:00+08:00");

function coupon(overrides: Partial<MemberCoupon>): MemberCoupon {
  return {
    couponId: "c1",
    templateId: "cg_001",
    title: "满30减5",
    status: "TAKE",
    valueFen: 500,
    thresholdFen: 3000,
    deductedFen: 0,
    validFrom: "2026-08-01",
    validUntil: "2026-12-31",
    orderNo: "",
    ...overrides,
  };
}

test("可用券：TAKE 且生效期内", () => {
  const view = classifyCouponStatus(coupon({}), NOW);
  assert.equal(view.tab, "available");
  assert.equal(view.note, "未使用");
});

test("已用券：CONSUME", () => {
  const view = classifyCouponStatus(coupon({ status: "CONSUME" }), NOW);
  assert.equal(view.tab, "used");
  assert.equal(view.note, "已使用");
});

test("已退回券：BACK 文案为已退回", () => {
  const view = classifyCouponStatus(coupon({ status: "BACK" }), NOW);
  assert.equal(view.tab, "refunded");
  assert.equal(view.note, "已退回");
});

test("已过期券：TAKE 且 validUntil 早于今天", () => {
  const view = classifyCouponStatus(coupon({ validUntil: "2026-08-01" }), NOW);
  assert.equal(view.tab, "expired");
  assert.equal(view.note, "已过期");
});

test("未生效券：TAKE 且 validFrom 晚于今天归入已过期组、角标未生效", () => {
  const view = classifyCouponStatus(coupon({ validFrom: "2026-09-01" }), NOW);
  assert.equal(view.tab, "expired");
  assert.equal(view.note, "未生效");
});

test("来源映射按 biz_type 优先级", () => {
  assert.equal(mapPointsSourceLabel({ amount: 100, total: 100, event_type: "order_award", source: "order", biz_type: "order_award" }), "订单奖励");
  assert.equal(mapPointsSourceLabel({ amount: -100, total: 0, event_type: "order_redeem", source: "order", biz_type: "order_redeem" }), "订单抵扣");
  assert.equal(mapPointsSourceLabel({ amount: 100, total: 100, event_type: "order_refund", source: "order", biz_type: "order_refund" }), "退款退回");
  assert.equal(mapPointsSourceLabel({ amount: 50, total: 150, event_type: "", source: "webhook", biz_type: "" }), "有赞同步");
  assert.equal(mapPointsSourceLabel({ amount: 50, total: 200, event_type: "", source: "import", biz_type: "" }), "导入");
});

test("支付分支：remain==0 走 free", () => {
  assert.equal(buildPaymentBranch({ remainFen: 0, balanceFen: 0, balanceEnabled: true }), "free");
});

test("支付分支：余额充足走 balance", () => {
  assert.equal(buildPaymentBranch({ remainFen: 3000, balanceFen: 5000, balanceEnabled: true }), "balance");
});

test("支付分支：余额部分抵扣走 combined", () => {
  assert.equal(buildPaymentBranch({ remainFen: 3000, balanceFen: 1000, balanceEnabled: true }), "combined");
});

test("支付分支：无余额或关闭余额走 online", () => {
  assert.equal(buildPaymentBranch({ remainFen: 3000, balanceFen: 0, balanceEnabled: true }), "online");
  assert.equal(buildPaymentBranch({ remainFen: 3000, balanceFen: 5000, balanceEnabled: false }), "online");
});

test("充值金额边界校验", () => {
  assert.equal(MIN_RECHARGE_FEN, 100);
  assert.equal(MAX_RECHARGE_FEN, 50000);
  assert.equal(isValidRechargeAmount(100), true);
  assert.equal(isValidRechargeAmount(50000), true);
  assert.equal(isValidRechargeAmount(99), false);
  assert.equal(isValidRechargeAmount(50001), false);
  assert.equal(isValidRechargeAmount(0), false);
});
