import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildOrderAmountView,
  formatOrderDisplayId,
  isBeijingDelivery,
  maskReceiverPhone,
  type OrderAmountSnapshot,
} from "../../miniprogram/utils/order-summary.ts";

function order(overrides: Partial<OrderAmountSnapshot>): OrderAmountSnapshot {
  return {
    totalFen: 19800,
    goodsTotalFen: 19800,
    deliveryFeeFen: 0,
    payableFen: 19800,
    deliveryType: "pickup",
    fulfillmentMethod: "pickup",
    ...overrides,
  };
}

test("订单列表手机号只展示脱敏后的联系信息", () => {
  assert.equal(maskReceiverPhone("18800000000"), "188****0000");
  assert.equal(maskReceiverPhone(" 19900001234 "), "199****1234");
  assert.equal(maskReceiverPhone("400-800-1234"), "400****1234");
  assert.equal(maskReceiverPhone(""), "手机号待确认");
});

test("订单列表使用可读短号，保留日期和尾号", () => {
  assert.equal(
    formatOrderDisplayId("mp_20260912_6f4b2c21_30fc29b0"),
    "2026-09-12 · 30FC29B0"
  );
  assert.equal(formatOrderDisplayId("short-order"), "short-order");
  assert.equal(formatOrderDisplayId(""), "待同步");
});

test("自提订单展示商品金额、零运费和服务端应付金额", () => {
  const view = buildOrderAmountView(order({}));

  assert.equal(view.deliveryTypeText, "到店自提");
  assert.equal(view.goodsTotalText, "¥198.00");
  assert.equal(view.deliveryFeeText, "¥0.00");
  assert.equal(view.totalText, "¥198.00");
  assert.equal(view.deliveryFeePending, false);
});

test("北京闪送订单展示商品金额、闪送费和服务端 payableFen", () => {
  const view = buildOrderAmountView(order({
    totalFen: 22400,
    deliveryFeeFen: 2600,
    payableFen: 21400,
    fulfillmentMethod: "beijing_delivery",
  }));

  assert.equal(view.deliveryTypeText, "北京闪送");
  assert.equal(view.goodsTotalText, "¥198.00");
  assert.equal(view.deliveryFeeText, "¥26.00");
  assert.equal(view.totalText, "¥214.00");
  assert.equal(view.payableText, "¥214.00");
});

test("北京闪送费未知时显示待确认而不是零元", () => {
  const view = buildOrderAmountView(order({
    deliveryFeeFen: null,
    fulfillmentMethod: "beijing_delivery",
  }));

  assert.equal(view.deliveryFeeText, "待确认");
  assert.equal(view.deliveryFeePending, true);
});

test("旧 deliveryType 字段仍可识别北京闪送", () => {
  assert.equal(isBeijingDelivery(order({ deliveryType: "delivery", fulfillmentMethod: undefined })), true);
  assert.equal(isBeijingDelivery(order({ deliveryType: "beijing_delivery", fulfillmentMethod: undefined })), true);
  assert.equal(isBeijingDelivery(order({ deliveryType: "pickup", fulfillmentMethod: "pickup" })), false);
});
