import { test } from "node:test";
import assert from "node:assert/strict";
import {
  formatMsgTime,
  normalizeTimeString,
} from "../../miniprogram/utils/time-format.ts";

// 本机时区为 UTC+8（Node 环境直接以本地时区解析 T 分隔字符串）
const EXPECTED_UTC8 = { h: 12, m: 30 };

test("normalizeTimeString 将空格分隔时间归一化为 ISO", () => {
  assert.equal(
    normalizeTimeString("2026-08-25 12:30:45"),
    "2026-08-25T12:30:45",
  );
});

test("normalizeTimeString 对已是 ISO 的输入原样返回", () => {
  assert.equal(
    normalizeTimeString("2026-08-25T12:30:45"),
    "2026-08-25T12:30:45",
  );
});

test("formatMsgTime 对 yyyy-MM-dd HH:mm:ss 生成有效 Date 且时间正确", () => {
  const result = formatMsgTime("2026-08-25 12:30:45");
  assert.match(result, /^\d{2}:\d{2}$/);
  const [hh, mm] = result.split(":").map(Number);
  assert.equal(hh, EXPECTED_UTC8.h);
  assert.equal(mm, EXPECTED_UTC8.m);
});

test("formatMsgTime 对 ISO 格式也输出正确时间", () => {
  const result = formatMsgTime("2026-08-25T12:30:45");
  const [hh, mm] = result.split(":").map(Number);
  assert.equal(hh, EXPECTED_UTC8.h);
  assert.equal(mm, EXPECTED_UTC8.m);
});

test("formatMsgTime 空串与非法串返回空字符串", () => {
  assert.equal(formatMsgTime(""), "");
  assert.equal(formatMsgTime("not-a-date"), "");
});
