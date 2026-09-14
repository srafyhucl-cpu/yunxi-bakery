import { test } from "node:test";
import assert from "node:assert/strict";

import {
  getAddressDetailText,
  isAddressDetailedEnough,
} from "../../miniprogram/utils/address.ts";

test("北京的行政区文本不算完整收货地址", () => {
  assert.equal(isAddressDetailedEnough("北京市东城区"), false);
  assert.equal(isAddressDetailedEnough("朝阳区"), false);
  assert.equal(isAddressDetailedEnough("北京市"), false);
});

test("包含小区、楼栋或门牌号后视为可继续履约", () => {
  assert.equal(isAddressDetailedEnough("北京市东城区南竹杆胡同2号银河SOHO"), true);
  assert.equal(isAddressDetailedEnough("北京市朝阳区测试路 1 号"), true);
  assert.equal(isAddressDetailedEnough("银河SOHO D座 1201"), true);
  assert.equal(getAddressDetailText("北京市朝阳区测试路 1 号"), "测试路1号");
});
