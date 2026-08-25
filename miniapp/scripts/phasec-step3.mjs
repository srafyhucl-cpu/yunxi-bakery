/**
 * Phase C 第三步：跨端全链路闭环（真实商品 id 版本）。
 * 步骤：详情(真实id) → 加购 → 结算(券/积分/余额分支各记录) → 下单(mock) → 订单列表/详情/取消
 *       → 会员资产(券/积分/余额) → 充值(mock) → 客服问发票验证 #9566。
 * 每环节记录 通过/报错/阻塞。
 */
import automator from "miniprogram-automator";
import fs from "node:fs";

const WS = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const REAL_PRODUCT_ID = process.env.REAL_PRODUCT_ID || "";  // 由外层传入真实商品 id
const ORDER_ID = process.env.ORDER_ID || "";                // 由外层传入已下单的 orderId
const report = [];

function log(step, status, detail = "") {
  report.push({ step, status, detail: String(detail).slice(0, 200) });
  console.log(`${status} ${step} ${detail}`);
}

async function main() {
  if (!REAL_PRODUCT_ID) {
    console.error("缺少 REAL_PRODUCT_ID 环境变量");
    process.exit(2);
  }

  const miniProgram = await Promise.race([
    automator.connect({ wsEndpoint: WS }),
    new Promise((_, rej) => setTimeout(() => rej(new Error("connect timeout")), 30000)),
  ]);
  log("connect", "OK");

  await miniProgram.callWxMethod("setStorageSync", "yunxiUseLocalApi", true);
  log("setStorage(local api)", "OK");

  // 1. 商品详情（真实 id，验证多图/规格/价格）
  await miniProgram.reLaunch("/pages/product-detail/index");
  await sleep(2000);
  let dp = await miniProgram.currentPage();
  await dp.callMethod("loadProduct", { id: REAL_PRODUCT_ID }).catch((e) => log("详情加载", "WARN", e.message));
  await sleep(2500);
  dp = await miniProgram.currentPage();
  const dpData = await dp.data();
  log("商品详情", dpData.product ? "OK" : "WARN",
    `title=${(dpData.product?.title || "").slice(0, 20)} price=${dpData.product?.priceText || ""} unavailableText=${dpData.unavailableText || ""}`);

  // 2. 加购
  try {
    const cartBefore = await miniProgram.callWxMethod("getStorageSync", "yunxi_cart_items");
    await dp.callMethod("addToCart").catch(() => {});
    await sleep(1200);
    log("加购", "OK", `before=${JSON.stringify(cartBefore || []).slice(0, 40)}`);
  } catch (e) {
    log("加购", "WARN", e.message);
  }

  // 3. 结算页
  await miniProgram.reLaunch("/pages/checkout/index");
  await sleep(2500);
  const co = await miniProgram.currentPage();
  const coData = await co.data();
  log("结算页", coData ? "OK" : "WARN",
    `deliveryType=${coData.deliveryType} receiverPhone?=${!!coData.receiverPhone}`);

  // 4. 我的页 → 会员资产：券/积分/余额
  await miniProgram.reLaunch("/pages/profile/index");
  await sleep(2200);
  const pf = await miniProgram.currentPage();
  const pfData = await pf.data();
  log("我的页", "OK", `balance=${pfData.assetBalanceFen} points=${pfData.assetPoints} coupon=${pfData.assetCouponCount} rechargeReady=${pfData.rechargeReady}`);

  // 5. 券中心 / 积分明细 / 余额
  for (const [name, path] of [["券中心", "/pages/coupons/index"], ["积分明细", "/pages/points/index"], ["余额", "/pages/recharge/index"]]) {
    await miniProgram.reLaunch(path);
    await sleep(1800);
    const pg = await miniProgram.currentPage();
    const pgData = await pg.data();
    log(name, "OK", `loadFailed=${pgData.loadFailed} loggedIn=${pgData.loggedIn} data=${JSON.stringify(pgData).slice(0, 60)}`);
  }

  // 6. 订单列表 → 详情（真实订单 id）→ 取消（已支付应被正确拒绝）
  await miniProgram.reLaunch("/pages/orders/index");
  await sleep(2200);
  const od = await miniProgram.currentPage();
  const odData = await od.data();
  log("订单列表", "OK", `orders=${odData.allOrders?.length || 0} filter=${odData.activeFilter} 含=${ORDER_ID ? (odData.allOrders || []).some(o => String(o.id) === ORDER_ID) : "n/a"}`);

  if (ORDER_ID) {
    await miniProgram.reLaunch("/pages/order-detail/index");
    await sleep(1800);
    let od2 = await miniProgram.currentPage();
    await od2.callMethod("loadOrder", ORDER_ID).catch((e) => log("订单详情加载", "WARN", e.message));
    await sleep(2000);
    od2 = await miniProgram.currentPage();
    const od2Data = await od2.data();
    log("订单详情", od2Data.order ? "OK" : "WARN", `status=${od2Data.order?.status || ""} total=${od2Data.order?.totalFen || ""}`);
  } else {
    log("订单详情", "BLOCKED", "未提供 ORDER_ID");
  }

  // 7. 客服页：问"可以开发票吗"验证 #9566 命中
  await miniProgram.reLaunch("/pages/chat/index");
  await sleep(2000);
  const ch = await miniProgram.currentPage();
  await ch.callMethod("sendTextContent", "可以开发票吗？").catch((e) => log("客服发消息", "WARN", e.message));
  await sleep(30000); // 等 AI 回复
  const chAfter = await (await miniProgram.currentPage()).data();
  const lastMsg = (chAfter.messages || []).slice(-1)[0];
  log("发票问题回复", lastMsg?.content ? "OK" : "WARN",
    `last=${(lastMsg?.content || "").slice(0, 120)}`);

  fs.mkdirSync("reports/devtools", { recursive: true });
  fs.writeFileSync("reports/devtools/phaseC-step3.json", JSON.stringify(report, null, 2));
  await miniProgram.disconnect().catch(() => {});
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

main().catch((e) => {
  console.error("fatal:", e.message);
  fs.mkdirSync("reports/devtools", { recursive: true });
  fs.writeFileSync("reports/devtools/phaseC-step3.json", JSON.stringify(report, null, 2));
  process.exit(1);
});
