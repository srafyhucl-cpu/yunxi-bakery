const automator = require("miniprogram-automator");
const fs = require("node:fs");

const WS_ENDPOINT = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const REPORT_PATH = "reports/devtools/product-purchase-path-audit.json";
const CART_STORAGE_KEY = "cartItems";
const PRODUCTS_ROUTE = "pages/products/index";
const PRODUCT_DETAIL_ROUTE = "pages/product-detail/index";
const CART_ROUTE = "pages/cart/index";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getExpectedRoute(route) {
  return route.split("?")[0];
}

async function waitForPage(miniProgram, route, isTabPage = false) {
  const expectedRoute = getExpectedRoute(route);
  if (isTabPage) {
    await miniProgram.switchTab(`/${route}`);
  } else {
    await miniProgram.reLaunch(`/${route}`);
  }

  for (let index = 0; index < 10; index += 1) {
    await sleep(300);
    const page = await miniProgram.currentPage();
    if (page.path === expectedRoute) {
      return page;
    }
  }

  return miniProgram.currentPage();
}

async function waitForValue(readValue, description) {
  for (let index = 0; index < 10; index += 1) {
    const value = await readValue();
    if (value) {
      return value;
    }
    await sleep(300);
  }
  throw new Error(`等待${description}超时`);
}

function findPurchasableProduct(catalogData) {
  const products = Array.isArray(catalogData.allProducts)
    ? catalogData.allProducts
    : Array.isArray(catalogData.categorySections)
      ? catalogData.categorySections.flatMap((section) => section.products || [])
      : [];
  return products.find((product) => product && product.isActive && Number(product.stock) > 0);
}

async function main() {
  const report = {
    generatedAt: new Date().toISOString(),
    status: "FAIL",
    checks: [],
    errors: []
  };
  let miniProgram;

  try {
    miniProgram = await automator.connect({ wsEndpoint: WS_ENDPOINT });
    await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);

    const catalog = await waitForPage(miniProgram, PRODUCTS_ROUTE, true);
    if (catalog.path !== PRODUCTS_ROUTE) {
      throw new Error(`商品页路由错误：${catalog.path}`);
    }
    const product = await waitForValue(
      async () => findPurchasableProduct(await catalog.data()),
      "在售商品列表"
    );
    report.checks.push({
      state: "catalog-product-selection",
      productId: product.id,
      title: product.title,
      stock: product.stock,
      priceFen: product.priceFen
    });

    const detail = await waitForPage(
      miniProgram,
      `${PRODUCT_DETAIL_ROUTE}?id=${encodeURIComponent(product.id)}`
    );
    if (detail.path !== PRODUCT_DETAIL_ROUTE) {
      throw new Error(`商品详情路由错误：${detail.path}`);
    }
    const detailData = await waitForValue(
      async () => {
        const data = await detail.data();
        return data.product ? data : null;
      },
      "商品详情"
    );
    const fulfillmentCard = await detail.$(".detail-fulfillment-card");
    const actions = await detail.$(".detail-actions");
    const actionButtons = actions ? await actions.$$("button") : [];
    const actionTexts = [];
    for (const button of actionButtons) {
      actionTexts.push((await button.text()).trim());
    }
    const actionsOffset = actions ? await actions.offset() : null;
    const actionsSize = actions ? await actions.size() : null;
    const systemInfo = await miniProgram.systemInfo();
    const viewportHeight = Number(systemInfo.windowHeight || systemInfo.screenHeight || 0);

    report.checks.push({
      state: "product-detail",
      canPurchase: detailData.canPurchase,
      hasFulfillmentCard: Boolean(fulfillmentCard),
      hasActions: Boolean(actions),
      actionTexts,
      actionsOffset,
      actionsSize,
      viewportHeight
    });

    if (!detailData.canPurchase || !fulfillmentCard || !actions) {
      throw new Error("在售商品详情缺少履约信息或购买操作");
    }
    if (!actionTexts.includes("加入购物车") || !actionTexts.includes("立即购买")) {
      throw new Error("在售商品详情缺少加入购物车或立即购买操作");
    }
    if (
      actionsOffset &&
      actionsSize &&
      viewportHeight > 0 &&
      (actionsOffset.top < 0 || actionsOffset.top + actionsSize.height > viewportHeight + 2)
    ) {
      throw new Error("商品详情购买操作未完整处于可视区域");
    }

    const addToCartIndex = actionTexts.findIndex((text) => text === "加入购物车");
    const addToCartButton = addToCartIndex >= 0 ? actionButtons[addToCartIndex] : null;
    if (!addToCartButton) {
      throw new Error("未找到加入购物车按钮");
    }
    await addToCartButton.tap();
    const cartItems = await waitForValue(
      async () => {
        const items = await miniProgram.callWxMethod("getStorageSync", CART_STORAGE_KEY);
        return Array.isArray(items) && items.some((item) => item.productId === product.id) ? items : null;
      },
      "购物车写入"
    );
    const matchingItem = cartItems.find((item) => item.productId === product.id);
    if (!matchingItem || matchingItem.quantity !== 1) {
      throw new Error("加入购物车后商品数量不正确");
    }

    const cart = await waitForPage(miniProgram, CART_ROUTE, true);
    if (cart.path !== CART_ROUTE) {
      throw new Error(`购物车路由错误：${cart.path}`);
    }
    const cartData = await waitForValue(
      async () => {
        const data = await cart.data();
        return data.hasItems ? data : null;
      },
      "购物车商品行"
    );
    const cartItem = await cart.$(".cart-item");
    const cartFooter = await cart.$(".cart-footer");
    const cartItemOffset = cartItem ? await cartItem.offset() : null;
    const cartItemSize = cartItem ? await cartItem.size() : null;
    const cartFooterOffset = cartFooter ? await cartFooter.offset() : null;

    report.checks.push({
      state: "cart-after-add",
      hasItems: cartData.hasItems,
      totalText: cartData.totalText,
      hasCartItem: Boolean(cartItem),
      hasCartFooter: Boolean(cartFooter),
      cartItemOffset,
      cartItemSize,
      cartFooterOffset
    });

    if (!cartItem || !cartFooter) {
      throw new Error("加入购物车后缺少商品行或结算栏");
    }
    if (cartItemOffset && cartItemSize && cartFooterOffset && cartFooterOffset.top < cartItemOffset.top + cartItemSize.height) {
      throw new Error("购物车结算栏遮挡商品行");
    }

    report.status = "PASS";
  } catch (error) {
    report.errors.push(error instanceof Error ? error.message : String(error));
  } finally {
    if (miniProgram) {
      try {
        await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);
      } catch (error) {
        report.errors.push(`购物车清理失败：${error instanceof Error ? error.message : String(error)}`);
      }
      await miniProgram.disconnect();
    }
    fs.mkdirSync("reports/devtools", { recursive: true });
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
  }

  console.log(`Product purchase path audit: ${report.status}`);
  console.log(`Report written to: ${REPORT_PATH}`);
  for (const error of report.errors) {
    console.error(`  x ${error}`);
  }
  if (report.status !== "PASS") {
    process.exit(1);
  }
}

main();
