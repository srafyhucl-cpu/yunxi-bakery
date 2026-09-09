import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildOrderAmountView,
  isBeijingDelivery,
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
