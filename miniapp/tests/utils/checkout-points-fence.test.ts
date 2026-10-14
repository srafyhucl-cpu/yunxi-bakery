import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

function readFixture(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

test("积分抵扣后端围栏关闭时，结算页不能暴露可选择积分入口", () => {
  const pointsFence = readFixture(
    "../../../backend/app/service/points/payment.py"
  );
  const checkoutSource = readFixture(
    "../../miniprogram/pages/checkout/index.ts"
  );
  const checkoutTemplate = readFixture(
    "../../miniprogram/pages/checkout/index.wxml"
  );

  assert.match(pointsFence, /POINTS_DEDUCTION_FENCE\s*=\s*True/);
  assert.equal(checkoutSource.includes("async applyPoints(orderId)"), false);
  assert.equal(checkoutSource.includes("onPointsSwitch"), false);
  assert.equal(checkoutSource.includes("togglePointsRow"), false);
  assert.equal(
    checkoutTemplate.includes('checked="{{pointsEnabled}}"'),
    false
  );
  assert.equal(checkoutTemplate.includes('bindchange="onPointsSwitch"'), false);
});
