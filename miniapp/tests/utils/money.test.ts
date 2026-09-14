import { test } from "node:test";
import assert from "node:assert/strict";

import { formatDeductionFen, formatFen } from "../../miniprogram/utils/money.ts";

test("formatFen 保留两位小数", () => {
  assert.equal(formatFen(0), "¥0.00");
  assert.equal(formatFen(500), "¥5.00");
  assert.equal(formatFen(2680), "¥26.80");
});

test("无抵扣时统一显示占位符，不再出现 -¥0.00", () => {
  assert.equal(formatDeductionFen(0), "-");
  assert.equal(formatDeductionFen(-100), "-");
});

test("存在抵扣时显示负向金额", () => {
  assert.equal(formatDeductionFen(100), "-¥1.00");
  assert.equal(formatDeductionFen(2680), "-¥26.80");
});
