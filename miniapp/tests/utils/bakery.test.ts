import { test } from "node:test";
import assert from "node:assert/strict";

import {
  getProductActionLabel,
  getProductAddToastLabel,
  getProductAvailabilityLabel,
  getProductCardTip,
  getProductPriceText,
  getProductPurchaseHint,
  isAccessoryProduct,
} from "../../miniprogram/utils/bakery.ts";

test("数字蜡烛按现货配件提示，不承诺提前一天预订", () => {
  const product = {
    title: "数字蜡烛",
    categoryName: "蛋糕",
    stock: 9051,
    tags: [],
  };

  assert.equal(isAccessoryProduct(product), true);
  assert.equal(
    getProductPurchaseHint(product),
    "现货可直接下单，闪送费下单前确认"
  );
});

test("蛋糕标题中的蜡烛说明不会被误判为配件", () => {
  const product = {
    title: "心型玫瑰花蛋糕（图片中的烟花蜡烛断货）",
    categoryName: "蛋糕",
    stock: 8,
    tags: [],
  };

  assert.equal(isAccessoryProduct(product), false);
  assert.equal(getProductPurchaseHint(product), "建议提前1天预订");
});

test("通用蛋糕分类不能覆盖无蛋糕语义的餐具商品", () => {
  const product = {
    title: "餐具（5人份）",
    categoryName: "蛋糕",
    tags: [],
  };

  assert.equal(isAccessoryProduct(product), true);
  assert.equal(
    getProductPurchaseHint(product),
    "配件库存以下单前确认为准"
  );
});

test("真实现货或当日标签优先表达可当天取", () => {
  assert.equal(
    getProductPurchaseHint({
      title: "招牌牛奶吐司",
      categoryName: "面包",
      tags: ["现货"],
    }),
    "有现货时可当天取，建议先确认"
  );
});

test("现货配件的标签、按钮与提示保持一致", () => {
  const candle = {
    title: "数字蜡烛",
    categoryName: "蛋糕",
    stock: 9051,
    tags: [],
    isActive: true,
  };

  assert.equal(getProductAvailabilityLabel(candle), "现货");
  assert.equal(getProductActionLabel(candle), "加入购物车");
  assert.equal(getProductAddToastLabel(candle), "已加入购物车");
  assert.equal(getProductCardTip(candle), "现货 · 闪送费另计");
});

test("现做商品不再重复展示可预订标签", () => {
  const toast = {
    title: "招牌牛奶吐司",
    categoryName: "面包",
    stock: 20,
    tags: [],
    isActive: true,
  };

  assert.equal(getProductAvailabilityLabel(toast), "");
  assert.equal(getProductActionLabel(toast), "预订");
  assert.equal(getProductAddToastLabel(toast), "已加入预订单");
  assert.equal(getProductCardTip(toast), "提前1天预订 · 闪送/自取");
});

test("低库存与不可售状态只表达异常事实", () => {
  const cake = { title: "足球之星", categoryName: "蛋糕", tags: [] };

  assert.equal(getProductAvailabilityLabel({ ...cake, stock: 3, isActive: true }), "仅余 3 件");
  assert.equal(getProductAvailabilityLabel({ ...cake, stock: 0, isActive: true }), "暂时售罄");
  assert.equal(getProductAvailabilityLabel({ ...cake, stock: 8, isActive: false }), "已下架");
  assert.equal(getProductActionLabel({ ...cake, stock: 0, isActive: true }), "查看");
  assert.equal(getProductCardTip({ ...cake, stock: 0, isActive: true }), "可咨询客服或先看其他商品");
});

test("非卖品与虚拟价格条目只能展示，不得生成下单动作", () => {
  const displayOnly = {
    title: "新西兰安佳动物奶油（非卖品仅展示）",
    categoryName: "原料展示",
    stock: 99999,
    tags: [],
    isActive: true,
    isPurchasable: false,
  };

  assert.equal(isAccessoryProduct(displayOnly), false);
  assert.equal(getProductAvailabilityLabel(displayOnly), "仅供展示");
  assert.equal(getProductActionLabel(displayOnly), "查看");
  assert.equal(getProductPurchaseHint(displayOnly), "仅用于原料或产品展示，不参与下单");
  assert.equal(getProductCardTip(displayOnly), "仅供展示 · 如有需要请联系客服");
  assert.equal(getProductAddToastLabel(displayOnly), "仅供展示，不可加入购物车");
  // 同步数据里的 9999900 分是商家设置的虚拟占位价，不得当作真实售价展示
  assert.equal(getProductPriceText(displayOnly, "¥99999.00"), "非卖品");
  assert.equal(
    getProductPriceText({ title: "招牌牛奶吐司", stock: 20, isActive: true }, "¥15.00"),
    "¥15.00"
  );
});

test("带现货标签的商品仍展示现货事实", () => {
  assert.equal(
    getProductAvailabilityLabel({ title: "招牌牛奶吐司", stock: 20, tags: ["现货"], isActive: true }),
    "现货"
  );
});
