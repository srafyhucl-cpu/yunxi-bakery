const automator = require("miniprogram-automator");
const fs = require("node:fs");
const { finalizeAuditStatus, exitForAuditStatus } = require("./lib/devtools-audit-status.cjs");

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
  // 商品页只保留服务端分页结果，首屏 activeProducts 就是目录选购入口。
  const products = Array.isArray(catalogData.activeProducts) ? catalogData.activeProducts : [];
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

    const serviceIcons = await detail.$$(".detail-service__icon");
    const serviceLabels = await detail.$$(".detail-service__label");
    const serviceIconAudits = [];
    for (const icon of serviceIcons) {
      const iconText = (await icon.text()).trim();
      const backgroundImage = await icon.style("background-image");
      const iconSize = await icon.size();
      serviceIconAudits.push({
        text: iconText,
        backgroundImage,
        size: `${Math.round(iconSize.width)}x${Math.round(iconSize.height)}`
      });
    }
    const serviceLabelTexts = [];
    for (const label of serviceLabels) {
      serviceLabelTexts.push((await label.text()).trim());
    }
    report.checks.push({
      state: "product-detail-service-icons",
      count: serviceIcons.length,
      labels: serviceLabelTexts,
      icons: serviceIconAudits
    });
    if (serviceIcons.length !== 2 || serviceLabels.length !== 2) {
      throw new Error("商品详情底部必须保留客服与购物车两个服务入口");
    }
    if (!serviceLabelTexts.includes("客服") || !serviceLabelTexts.includes("购物车")) {
      throw new Error(`商品详情服务入口文案异常：${serviceLabelTexts.join("、")}`);
    }
    for (const iconAudit of serviceIconAudits) {
      if (iconAudit.text) {
        throw new Error(`商品详情服务入口仍在用文字充当图标：${iconAudit.text}`);
      }
      if (!iconAudit.backgroundImage || iconAudit.backgroundImage === "none") {
        throw new Error("商品详情服务入口图标未渲染");
      }
      const [width, height] = iconAudit.size.split("x").map(Number);
      if (width < 18 || height < 18) {
        throw new Error(`商品详情服务入口图标过小：${iconAudit.size}`);
      }
    }

    if (
      actionsOffset &&
      actionsSize &&
      viewportHeight > 0 &&
      (actionsOffset.top < 0 || actionsOffset.top + actionsSize.height > viewportHeight + 2)
    ) {
      throw new Error("商品详情购买操作未完整处于可视区域");
    }

    // 底部常驻操作栏与滚动内容的安全距离：既不能遮挡最后一段内容，也不能留出大片空白。
    const detailScrollView = await detail.$(".page-scroll");
    if (!detailScrollView || !actionsOffset) {
      throw new Error("商品详情缺少可测量的滚动容器或底部操作栏");
    }
    const sectionElements = await detail.$$(".detail-content > .detail-section");
    if (sectionElements.length === 0) {
      throw new Error("商品详情未找到可测量的内容分区");
    }
    await detailScrollView.scrollTo(0, 100000);
    await sleep(500);
    const lastSection = sectionElements[sectionElements.length - 1];
    const lastSectionOffset = await lastSection.offset();
    const lastSectionSize = await lastSection.size();
    const footerGap = actionsOffset.top - (lastSectionOffset.top + lastSectionSize.height);
    report.checks.push({
      state: "product-detail-footer-gap",
      lastSectionBottom: Number((lastSectionOffset.top + lastSectionSize.height).toFixed(2)),
      actionsTop: Number(actionsOffset.top.toFixed(2)),
      gap: Number(footerGap.toFixed(2))
    });
    if (footerGap < 0) {
      throw new Error(`商品详情底部操作栏遮挡最后一段内容：间隙 ${footerGap.toFixed(2)}px`);
    }
    try {
      fs.mkdirSync("reports/devtools", { recursive: true });
      await miniProgram.screenshot({
        path: "reports/devtools/final-product-detail-footer.png",
        fullPage: false
      });
    } catch (error) {
      report.checks.push({
        state: "product-detail-footer-screenshot",
        ok: false,
        error: error instanceof Error ? error.message : String(error)
      });
    }
    if (footerGap > 48) {
      throw new Error(`商品详情底部留下过大空白：间隙 ${footerGap.toFixed(2)}px`);
    }
    await detailScrollView.scrollTo(0, 0);
    await sleep(300);

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
    const cartTitle = await cart.$(".cart-item .cart-title");
    const cartItemOffset = cartItem ? await cartItem.offset() : null;
    const cartItemSize = cartItem ? await cartItem.size() : null;
    const cartFooterOffset = cartFooter ? await cartFooter.offset() : null;
    const cartTitleSize = cartTitle ? await cartTitle.size() : null;
    const cartTitleLineClamp = cartTitle
      ? await cartTitle.style("-webkit-line-clamp")
      : "";
    const cartTitleWhiteSpace = cartTitle ? await cartTitle.style("white-space") : "";
    const cartTitleDisplay = cartTitle ? await cartTitle.style("display") : "";
    if (cartTitle) {
      report.checks.push({
        state: "cart-title-layout",
        lineClamp: cartTitleLineClamp,
        display: cartTitleDisplay,
        whiteSpace: cartTitleWhiteSpace,
        titleSize: cartTitleSize,
        cartItemSize,
      });
      if (Number(cartTitleLineClamp) !== 2 || cartTitleWhiteSpace === "nowrap") {
        throw new Error("购物车商品名未按两行展示");
      }
      if (!cartTitleSize || cartTitleSize.width < 180 || cartTitleSize.height < 34) {
        throw new Error(
          `购物车商品名可用区域过小：${cartTitleSize ? `${cartTitleSize.width}x${cartTitleSize.height}px` : "未知"}`
        );
      }
    } else {
      throw new Error("购物车商品行缺少商品名");
    }

    // 数量为 1 时减号必须保持减号语义：改成“✕”会让顾客误以为点击直接删除。
    const minusButton = await cart.$(".cart-item .stepper-btn--minus");
    const minusText = minusButton ? (await minusButton.text()).trim() : "";
    const minusSize = minusButton ? await minusButton.size() : null;
    report.checks.push({
      state: "cart-stepper-minus-at-one",
      quantity: Array.isArray(cartData.items) && cartData.items.length ? cartData.items[0].quantity : null,
      text: minusText,
      size: minusSize,
    });
    if (!minusButton) {
      throw new Error("购物车商品行缺少数量减号控件");
    }
    if (minusText !== "-") {
      throw new Error(`购物车减号语义错误：数量为 1 时显示“${minusText || "空"}”，应保持“-”并保留移除确认`);
    }
    if (!minusSize || minusSize.width < 44 || minusSize.height < 44) {
      throw new Error(
        `购物车减号触控区域不足 44px：${minusSize ? `${minusSize.width}x${minusSize.height}` : "未知"}`
      );
    }

    try {
      fs.mkdirSync("reports/devtools", { recursive: true });
      await miniProgram.screenshot({
        path: "reports/devtools/final-cart-real-product.png",
        fullPage: false,
      });
    } catch (error) {
      report.checks.push({
        state: "cart-screenshot",
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      });
    }

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
    report.status = finalizeAuditStatus(report);
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
  }

  console.log(`Product purchase path audit: ${report.status}`);
  console.log(`Report written to: ${REPORT_PATH}`);
  for (const error of report.errors) {
    console.error(`  x ${error}`);
  }
  if (report.blockedReason) {
    console.log(`  ! ${report.blockedReason}`);
  }
  exitForAuditStatus(report.status);
}

main();
