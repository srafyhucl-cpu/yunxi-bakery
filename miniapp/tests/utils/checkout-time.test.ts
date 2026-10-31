import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildCheckoutHourOptions,
  buildDefaultExpectTime,
  parseExpectTime,
  PREORDER_MIN_ADVANCE_HOURS,
  resolveCheckoutSchedule,
} from "../../miniprogram/utils/checkout-time.ts";

const BUSINESS_HOURS = "09:00-19:30";
const MINUTE_OPTIONS = ["00", "30"];
// 北京时间 2026-09-13 20:30：当天已过 17:00 截单，最早可预约日期为次日。
const AFTER_CUTOFF = new Date("2026-09-13T20:30:00+08:00");
const BEFORE_CUTOFF = new Date("2026-09-13T10:00:00+08:00");

test("parseExpectTime 解析合法时间并拒绝非法格式", () => {
  assert.deepEqual(parseExpectTime("2026-09-14 19:30"), {
    dateValue: "2026-09-14",
    hourValue: "19",
    minuteValue: "30",
  });
  assert.equal(parseExpectTime("2026-09-14 7:05")?.hourValue, "07");
  assert.equal(parseExpectTime("明天下午"), null);
  assert.equal(parseExpectTime(""), null);
});

test("resolveCheckoutSchedule 按已选时间还原选择器，而不是回到默认 18:00", () => {
  const schedule = resolveCheckoutSchedule(
    BUSINESS_HOURS,
    "2026-09-14 19:30",
    MINUTE_OPTIONS,
    AFTER_CUTOFF,
  );
  assert.equal(schedule.dateValue, "2026-09-14");
  assert.equal(schedule.hourOptions[schedule.hourIndex], "19");
  assert.equal(MINUTE_OPTIONS[schedule.minuteIndex], "30");
  assert.equal(schedule.expectTime, "2026-09-14 19:30");
});

test("resolveCheckoutSchedule 截单前保留当天预约", () => {
  const schedule = resolveCheckoutSchedule(
    BUSINESS_HOURS,
    "2026-09-13 18:00",
    MINUTE_OPTIONS,
    BEFORE_CUTOFF,
  );
  assert.equal(schedule.dateValue, "2026-09-13");
  assert.equal(
    schedule.expectTime,
    `${schedule.dateValue} ${schedule.hourOptions[schedule.hourIndex]}:${MINUTE_OPTIONS[schedule.minuteIndex]}`,
  );
});

test("resolveCheckoutSchedule 把已过截单日的旧时间抬到最早可预约日期", () => {
  const schedule = resolveCheckoutSchedule(
    BUSINESS_HOURS,
    "2026-09-13 10:00",
    MINUTE_OPTIONS,
    AFTER_CUTOFF,
  );
  assert.equal(schedule.dateValue, "2026-09-14");
  assert.equal(schedule.expectTime, "2026-09-14 10:00");
  assert.equal(
    schedule.expectTime,
    `${schedule.dateValue} ${schedule.hourOptions[schedule.hourIndex]}:${MINUTE_OPTIONS[schedule.minuteIndex]}`,
  );
});

test("resolveCheckoutSchedule 在没有有效提交值时回落到默认预约时间", () => {
  const schedule = resolveCheckoutSchedule(
    BUSINESS_HOURS,
    "",
    MINUTE_OPTIONS,
    AFTER_CUTOFF,
  );
  assert.equal(schedule.dateValue, "2026-09-14");
  assert.equal(schedule.expectTime, "2026-09-14 18:00");
  assert.equal(
    schedule.expectTime,
    `${schedule.dateValue} ${schedule.hourOptions[schedule.hourIndex]}:${MINUTE_OPTIONS[schedule.minuteIndex]}`,
  );
});

test("预订商品把最早可选小时抬到当前时间 + 4 小时", () => {
  // 北京时间 10:00 进结算页：普通商品最早 10 点，预订商品最早 14 点
  const normal = buildCheckoutHourOptions(
    BUSINESS_HOURS,
    "2026-09-13",
    BEFORE_CUTOFF,
  );
  const preorder = buildCheckoutHourOptions(
    BUSINESS_HOURS,
    "2026-09-13",
    BEFORE_CUTOFF,
    PREORDER_MIN_ADVANCE_HOURS,
  );
  assert.equal(normal[0], "10");
  assert.equal(preorder[0], "14");
});

test("预订提前量把当天时段挤完时，默认时间落到次日", () => {
  // 北京时间 16:30 + 4 小时 = 20:30，已超过 19:30 打烊，当天无可用时段
  const lateAfternoon = new Date("2026-09-13T16:30:00+08:00");
  const schedule = resolveCheckoutSchedule(
    BUSINESS_HOURS,
    "",
    MINUTE_OPTIONS,
    lateAfternoon,
    PREORDER_MIN_ADVANCE_HOURS,
  );
  assert.equal(schedule.dateValue, "2026-09-14");
  const defaultTime = buildDefaultExpectTime(
    BUSINESS_HOURS,
    lateAfternoon,
    PREORDER_MIN_ADVANCE_HOURS,
  );
  assert.equal(defaultTime.slice(0, 10), "2026-09-14");
});

test("提前量只影响当天，次日仍从营业开始时间起选", () => {
  const options = buildCheckoutHourOptions(
    BUSINESS_HOURS,
    "2026-09-14",
    BEFORE_CUTOFF,
    PREORDER_MIN_ADVANCE_HOURS,
  );
  assert.equal(options[0], "09");
});
