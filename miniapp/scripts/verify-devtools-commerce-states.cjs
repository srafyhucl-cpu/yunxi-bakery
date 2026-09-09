const automator = require("miniprogram-automator");
const fs = require("node:fs");

const WS_ENDPOINT = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const REPORT_PATH = "reports/devtools/commerce-state-audit.json";
const CART_STORAGE_KEY = "cartItems";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function navigateAndWait(miniProgram, route, isTabPage = false) {
  if (isTabPage) {
    await miniProgram.switchTab(`/${route}`);
  } else {
    await miniProgram.reLaunch(`/${route}`);
  }

  for (let index = 0; index < 8; index++) {
    await sleep(400);
    const page = await miniProgram.currentPage();
    if (page.path === route) {
      return page;
    }
  }

  return miniProgram.currentPage();
}

async function waitForElement(page, selector, description) {
  for (let index = 0; index < 10; index += 1) {
    const element = await page.$(selector);
    if (element) {
      return element;
    }
    await sleep(300);
  }
  throw new Error(`等待${description}超时`);
}

async function main() {
  const miniProgram = await automator.connect({ wsEndpoint: WS_ENDPOINT });
  const report = {
    generatedAt: new Date().toISOString(),
    status: "PASS",
    checks: [],
    errors: []
  };

  try {
    await miniProgram.callWxMethod("setStorageSync", CART_STORAGE_KEY, [
      {
        productId: "commerce-audit-item",
        title: "商品审查样本",
        imageUrl: "",
        priceFen: 19800,
        quantity: 2
      }
    ]);

    const cart = await navigateAndWait(miniProgram, "pages/cart/index", true);
    const cartData = await cart.data();
    const cartItem = await cart.$(".cart-item");
    const cartFooter = await cart.$(".cart-footer");
    const cartStepper = await cart.$(".cart-stepper");
    const cartItemOffset = cartItem ? await cartItem.offset() : null;
    const cartItemSize = cartItem ? await cartItem.size() : null;
    const cartFooterOffset = cartFooter ? await cartFooter.offset() : null;
    const cartFooterSize = cartFooter ? await cartFooter.size() : null;

    report.checks.push({
      page: cart.path,
      state: "cart-with-item",
      hasItems: cartData.hasItems,
      hasCartItem: Boolean(cartItem),
      hasCartFooter: Boolean(cartFooter),
      hasCartStepper: Boolean(cartStepper),
      cartItemOffset,
      cartItemSize,
      cartFooterOffset,
      cartFooterSize
    });

    if (!cartData.hasItems || !cartItem || !cartFooter || !cartStepper) {
      report.errors.push("有商品购物车缺少商品行、数量控件或结算栏");
    }
    if (cartItemOffset && cartItemSize && cartFooterOffset && cartFooterOffset.top < cartItemOffset.top + cartItemSize.height) {
      report.errors.push("有商品购物车结算栏遮挡商品行");
    }

    await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);
    const catalog = await navigateAndWait(miniProgram, "pages/products/index", true);
    const catalogAction = await catalog.$(".product-action-btn");
    const catalogActionText = catalogAction ? (await catalogAction.text()).trim() : "";
    const catalogActionSize = catalogAction ? await catalogAction.size() : null;
    const catalogCartBarBefore = await catalog.$(".products-cart-bar");
    const catalogStock = await catalog.$(".product-stock");
    const catalogHint = await catalog.$(".product-hint");
    const catalogHeading = await catalog.$(".products-heading");
    const catalogData = await catalog.data();
    if (catalogAction && catalogActionText === "预订") {
      await catalogAction.tap();
      await sleep(500);
    }
    const catalogCartBarAfter = await catalog.$(".products-cart-bar");
    const catalogCartStorage = await miniProgram.callWxMethod("getStorageSync", CART_STORAGE_KEY);

    report.checks.push({
      page: catalog.path,
      state: "catalog",
      productActionText: catalogActionText,
      productActionSize: catalogActionSize,
      cartBarVisibleBeforeQuickAdd: Boolean(catalogCartBarBefore),
      cartBarVisibleAfterQuickAdd: Boolean(catalogCartBarAfter),
      quickAddCartCount: Array.isArray(catalogCartStorage) ? catalogCartStorage.length : 0,
      hasStockLabel: Boolean(catalogStock),
      hasPurchaseHint: Boolean(catalogHint),
      hasActiveHeading: Boolean(catalogHeading),
      activeProductsCount: Array.isArray(catalogData.activeProducts) ? catalogData.activeProducts.length : 0
    });

    if (!catalogAction || !["预订", "查看"].includes(catalogActionText)) {
      report.errors.push("商品卡动作未表达预订或查看详情");
    }
    if (catalogActionSize && (catalogActionSize.width < 44 || catalogActionSize.height < 44)) {
      report.errors.push(`商品卡动作触控区域过小：${catalogActionSize.width}x${catalogActionSize.height}px，最小目标为44x44px`);
    }
    if (catalogActionText === "预订" && (!Array.isArray(catalogCartStorage) || catalogCartStorage.length === 0 || !catalogCartBarAfter)) {
      report.errors.push("商品目录预订动作未写入购物车或未展示预订单底栏");
    }
    if (!catalogStock || !catalogHint || !catalogHeading) {
      report.errors.push("商品目录缺少库存、预订提示或当前分类标题");
    }
    if (!Array.isArray(catalogData.activeProducts) || catalogData.activeProducts.length === 0) {
      report.errors.push("商品目录未渲染活动分类商品清单");
    }

    await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);
    const home = await navigateAndWait(miniProgram, "pages/home/index", true);
    const homeAction = await waitForElement(home, ".product-action", "首页商品预订按钮");
    const homeActionText = (await homeAction.text()).trim();
    const homeActionSize = await homeAction.size();
    const homeCartBarBefore = await home.$(".home-cart-bar");
    if (homeActionText === "预订") {
      await homeAction.tap();
      await sleep(500);
    }
    const homeCartBarAfter = await home.$(".home-cart-bar");
    const homeCartStorage = await miniProgram.callWxMethod("getStorageSync", CART_STORAGE_KEY);

    report.checks.push({
      page: home.path,
      state: "home-quick-add",
      productActionText: homeActionText,
      productActionSize: homeActionSize,
      cartBarVisibleBeforeQuickAdd: Boolean(homeCartBarBefore),
      cartBarVisibleAfterQuickAdd: Boolean(homeCartBarAfter),
      quickAddCartCount: Array.isArray(homeCartStorage) ? homeCartStorage.length : 0
    });

    if (!["预订", "查看"].includes(homeActionText)) {
      report.errors.push("首页商品动作未表达预订或查看详情");
    }
    if (homeActionSize && (homeActionSize.width < 44 || homeActionSize.height < 44)) {
      report.errors.push(`首页商品动作触控区域过小：${homeActionSize.width}x${homeActionSize.height}px，最小目标为44x44px`);
    }
    if (homeActionText === "预订" && (!Array.isArray(homeCartStorage) || homeCartStorage.length === 0 || !homeCartBarAfter)) {
      report.errors.push("首页商品预订动作未写入购物车或未展示预订单底栏");
    }

    const unavailableDetail = await navigateAndWait(miniProgram, "pages/product-detail/index");
    const unavailableData = await unavailableDetail.data();
    const unavailableActions = await unavailableDetail.$(".detail-actions");

    report.checks.push({
      page: unavailableDetail.path,
      state: "detail-without-id",
      canPurchase: unavailableData.canPurchase,
      hasPurchaseActions: Boolean(unavailableActions)
    });

    if (unavailableData.canPurchase === false && unavailableActions) {
      report.errors.push("不可购买商品仍展示购买操作");
    }
  } finally {
    await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);
    await miniProgram.disconnect();
  }

  if (report.errors.length > 0) {
    report.status = "FAIL";
  }
  fs.mkdirSync("reports/devtools", { recursive: true });
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
  console.log(`Commerce state audit: ${report.status}`);
  console.log(`Report written to: ${REPORT_PATH}`);

  if (report.errors.length > 0) {
    for (const error of report.errors) {
      console.error(`  x ${error}`);
    }
    process.exit(1);
  }
}

main().catch((error) => {
  console.error("Commerce state audit failed:", error);
  process.exit(1);
});
