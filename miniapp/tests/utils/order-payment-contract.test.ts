import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  ORDER_LIST_FILTERS,
  canPayOrder,
} from "../../miniprogram/constants/order.ts";

function readFixture(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("组合支付必须把后端返回的剩余支付会话交给支付执行器", () => {
  const checkoutSource = readFixture(
    "../../miniprogram/pages/checkout/index.ts"
  );
  const orderServiceSource = readFixture(
    "../../miniprogram/services/orders.ts"
  );

  assert.match(
    orderServiceSource,
    /export interface CombinedPaymentResponse[\s\S]*remainderPayment/
  );
  assert.match(
    checkoutSource,
    /const payment = await prepareCombinedPayment\(orderId, balanceFen\);[\s\S]*await executePreparedPayment\(payment\.remainderPayment\);/
  );
});

test("已支付订单再次准备支付时只读取订单，不重复发起微信支付", () => {
  const paymentSource = readFixture(
    "../../miniprogram/utils/order-payment.ts"
  );

  assert.match(
    paymentSource,
    /if \(payment\.paymentStatus === "paid"\)[\s\S]*return getOrder\(payment\.orderId\);/
  );
});

test("恢复待支付配送订单时保留原报价快照", () => {
  const checkoutSource = readFixture(
    "../../miniprogram/pages/checkout/index.ts"
  );

  assert.match(
    checkoutSource,
    /if \(this\.data\.deliveryType === "delivery" && !pendingMatchesCurrentOrder\)/,
  );
  assert.doesNotMatch(
    checkoutSource,
    /if \(this\.data\.deliveryType === "delivery"\) \{\s*void this\.fetchDeliveryQuote\(\);/
  );
});

test("组合支付外部支付取消后订单详情仍可继续支付", () => {
  const partialOrder = { status: "pending", paymentStatus: "partial" };
  assert.equal(canPayOrder(partialOrder), true);
  assert.equal(
    ORDER_LIST_FILTERS.find((filter) => filter.key === "unpaid")?.match(partialOrder),
    true
  );
  const checkoutSource = readFixture(
    "../../miniprogram/pages/checkout/index.ts"
  );
  assert.match(
    checkoutSource,
    /resumePartialRemainder[\s\S]*prepareOrderPayment\(orderId\)/
  );
  assert.match(
    checkoutSource,
    /paymentStatus:\s*"partial"/
  );
});

test("组合支付 partial 订单恢复时不得再次扣除当前余额", () => {
  const checkoutSource = readFixture(
    "../../miniprogram/pages/checkout/index.ts"
  );

  assert.match(
    checkoutSource,
    /pendingIsPartial[\s\S]*partialBalanceFen[\s\S]*resumePartialRemainder:\s*pendingIsPartial/
  );
  assert.match(
    checkoutSource,
    /const partialBalanceFen = pendingIsPartial[\s\S]*this\.data\.partialBalanceFen/
  );
  assert.match(
    checkoutSource,
    /payment:\s*payment\.remainderPayment|executePreparedPayment\(payment\.remainderPayment\)/
  );
});

test("未选优惠券的待支付订单不能被标记为已应用，已应用券不能换选", () => {
  const checkoutSource = readFixture(
    "../../miniprogram/pages/checkout/index.ts"
  );

  assert.match(
    checkoutSource,
    /if \(!pendingAssetsApplied && this\.data\.selectedCouponId\) \{[\s\S]*applyCoupon\(orderId, this\.data\.selectedCouponId\)[\s\S]*savePendingOrder\(orderId, \{ assetsApplied: true, couponFen \}\)/
  );
  assert.match(
    checkoutSource,
    /if \(this\.data\.orderLocked && this\.data\.assetsApplied\)[\s\S]*订单已锁定当前资产[\s\S]*return;/
  );
});
