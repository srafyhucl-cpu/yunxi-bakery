const automator = require("miniprogram-automator");
const fs = require("node:fs");
const {
  captureEvidenceScreenshot,
  finalizeAuditStatus,
  exitForAuditStatus
} = require("./lib/devtools-audit-status.cjs");

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
    const catalogStockText = catalogStock ? (await catalogStock.text()).trim() : "";
    if (catalogAction && ["预订", "加入购物车"].includes(catalogActionText)) {
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
      stockLabelText: catalogStockText,
      hasPurchaseHint: Boolean(catalogHint),
      hasActiveHeading: Boolean(catalogHeading),
      activeProductsCount: Array.isArray(catalogData.activeProducts) ? catalogData.activeProducts.length : 0
    });

    if (!catalogAction || !["预订", "加入购物车", "查看"].includes(catalogActionText)) {
      report.errors.push("商品卡动作未表达预订、加购或查看详情");
    }
    if (catalogActionSize && (catalogActionSize.width < 44 || catalogActionSize.height < 44)) {
      report.errors.push(`商品卡动作触控区域过小：${catalogActionSize.width}x${catalogActionSize.height}px，最小目标为44x44px`);
    }
    if (catalogActionText !== "查看" && (!Array.isArray(catalogCartStorage) || catalogCartStorage.length === 0 || !catalogCartBarAfter)) {
      report.errors.push("商品目录快捷动作未写入购物车或未展示预订单底栏");
    }
    if (!catalogHint || !catalogHeading) {
      report.errors.push("商品目录缺少履约提示或当前分类标题");
    }
    // 可用性标签只能是可核对事实；默认能力“可预订”不得回潮。
    if (catalogStockText && !/^(现货|暂时售罄|已下架|仅余 \d+ 件)$/.test(catalogStockText)) {
      report.errors.push(`商品卡可用性标签表达不可核对信息：${catalogStockText}`);
    }
    if (!Array.isArray(catalogData.activeProducts) || catalogData.activeProducts.length === 0) {
      report.errors.push("商品目录未渲染活动分类商品清单");
    }

    const catalogBadges = await catalog.$$(".product-badge");
    const catalogBadgeTexts = [];
    for (const badge of catalogBadges) {
      catalogBadgeTexts.push((await badge.text()).trim());
    }
    const allowedCatalogBadgeTexts = new Set(["现货", "暂时售罄", "已下架"]);
    const forbiddenCatalogBadgeTexts = new Set(["招牌", "热卖", "新品", "限量"]);
    const invalidCatalogBadgeTexts = catalogBadgeTexts.filter(
      (text) => text && !allowedCatalogBadgeTexts.has(text)
    );
    const inferredCatalogBadgeTexts = catalogBadgeTexts.filter((text) =>
      forbiddenCatalogBadgeTexts.has(text)
    );
    const catalogActiveProducts = Array.isArray(catalogData.activeProducts)
      ? catalogData.activeProducts
      : [];
    const catalogSoldNumbers = catalogActiveProducts
      .map((product) => {
        const match = /^已售\s*(\d+)$/.exec(String(product.soldText || "").trim());
        return match ? Number(match[1]) : null;
      })
      .filter((value) => value !== null);
    const catalogSalesOrdered = catalogSoldNumbers.every(
      (value, index) => index === 0 || catalogSoldNumbers[index - 1] >= value
    );

    report.checks.push({
      page: catalog.path,
      state: "catalog-badges-and-popularity",
      badgeTexts: catalogBadgeTexts,
      soldNumbers: catalogSoldNumbers,
      salesOrderedDescending: catalogSalesOrdered
    });

    if (invalidCatalogBadgeTexts.length > 0 || inferredCatalogBadgeTexts.length > 0) {
      const rejectedTexts = Array.from(
        new Set([...invalidCatalogBadgeTexts, ...inferredCatalogBadgeTexts])
      ).join("、");
      report.errors.push(`商品目录出现无数据来源的营销徽标：${rejectedTexts}`);
    }
    if (catalogSoldNumbers.length >= 2 && !catalogSalesOrdered) {
      report.errors.push(
        `商品目录未按真实销量降序排列：${catalogSoldNumbers.join("、")}`
      );
    }

    await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);
    const home = await navigateAndWait(miniProgram, "pages/home/index", true);
    const homeAction = await waitForElement(home, ".product-action", "首页商品预订按钮");
    const homeActionText = (await homeAction.text()).trim();
    const homeActionSize = await homeAction.size();
    const homeCartBarBefore = await home.$(".home-cart-bar");
    if (["预订", "加入购物车"].includes(homeActionText)) {
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

    if (!["预订", "加入购物车", "查看"].includes(homeActionText)) {
      report.errors.push("首页商品动作未表达预订、加购或查看详情");
    }
    if (homeActionSize && (homeActionSize.width < 44 || homeActionSize.height < 44)) {
      report.errors.push(`首页商品动作触控区域过小：${homeActionSize.width}x${homeActionSize.height}px，最小目标为44x44px`);
    }
    if (homeActionText !== "查看" && (!Array.isArray(homeCartStorage) || homeCartStorage.length === 0 || !homeCartBarAfter)) {
      report.errors.push("首页商品快捷动作未写入购物车或未展示预订单底栏");
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

    await miniProgram.callWxMethod("setStorageSync", CART_STORAGE_KEY, [
      {
        productId: "checkout-asset-state-item",
        title: "结算资产状态样本",
        imageUrl: "",
        priceFen: 19800,
        quantity: 1
      }
    ]);
    const checkout = await navigateAndWait(miniProgram, "pages/checkout/index");
    await checkout.setData({
      isLoggedIn: true,
      sessionView: {
        ...((await checkout.data()).sessionView || {}),
        statusText: "微信身份",
        badgeText: "已登录",
        actionText: "刷新信息",
        hintText: "当前身份可用于查询订单和会员资产",
        loggedIn: true
      },
      loginStateText: "订单将关联到当前微信身份",
      errorMessage: "",
      totalText: "¥198.00",
      checkoutItems: [
        {
          productId: "checkout-asset-state-item",
          title: "结算资产状态样本",
          imageUrl: "",
          priceFen: 19800,
          priceText: "¥198.00",
          quantity: 1
        }
      ],
      goodsFen: 19800,
      pointsBalance: 0,
      balanceFen: 0,
      pointsEnabled: true,
      balanceEnabled: true
    });
    await checkout.callMethod("applyAssetAvailability");
    await sleep(300);
    const checkoutAssetData = await checkout.data();
    const pointsSwitch = await checkout.$(".asset-switch--points");
    const balanceSwitch = await checkout.$(".asset-switch--balance");
    const sessionAction = await checkout.$(".session-notice__button");
    const benefitPanel = await checkout.$(".benefit-panel");
    const checkoutText = benefitPanel ? await benefitPanel.text() : "";
    report.checks.push({
      page: checkout.path,
      state: "zero-member-assets",
      pointsEnabled: checkoutAssetData.pointsEnabled,
      balanceEnabled: checkoutAssetData.balanceEnabled,
      pointsBalance: checkoutAssetData.pointsBalance,
      balanceFen: checkoutAssetData.balanceFen,
      pointsSwitchVisible: Boolean(pointsSwitch),
      balanceSwitchVisible: Boolean(balanceSwitch),
      sessionActionVisible: Boolean(sessionAction),
      benefitText: checkoutText.trim()
    });
    if (checkoutAssetData.pointsEnabled !== false || checkoutAssetData.balanceEnabled !== false) {
      report.errors.push("零积分或零余额时抵扣开关仍保持开启");
    }
    if (pointsSwitch || balanceSwitch) {
      report.errors.push("零资产时仍渲染不可用的抵扣开关");
    }
    if (sessionAction) {
      report.errors.push("已登录结算页会话提示仍展示返回按钮");
    }
    if (!checkoutText.includes("暂无可用积分") || !checkoutText.includes("暂无可用余额")) {
      report.errors.push("零资产抵扣项缺少明确的不可用说明");
    }
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/final-checkout-zero-assets.png");

    const orders = await navigateAndWait(miniProgram, "pages/orders/index");
    const ordersData = await orders.data();
    await orders.setData({
      canUseOrders: true,
      sessionView: { ...(ordersData.sessionView || {}), loggedIn: true },
      filteredOrders: [
        {
          id: "mp_20260912_6f4b2c21_30fc29b0",
          statusText: "制作中",
          paymentStatusText: "已支付",
          itemTitle: "草莓奶油蛋糕",
          itemCount: 1,
          orderNoText: "2026-09-12 · 30FC29B0",
          fulfillmentTypeText: "到店自提",
          receiverLabel: "联系人",
          receiverContactText: "张三 · 188****0000",
          expectTimeLabel: "预约取货",
          expectTimeText: "2026-09-13 15:00",
          createdAt: "2026-09-12 10:30",
          totalText: "¥198.00",
          canPay: false,
          canCancel: false
        }
      ]
    });
    await sleep(300);
    const orderNo = await orders.$(".order-id");
    const orderMeta = await orders.$(".order-meta");
    const orderNoText = orderNo ? (await orderNo.text()).trim() : "";
    const orderMetaText = orderMeta ? (await orderMeta.text()).trim() : "";
    report.checks.push({
      page: orders.path,
      state: "readable-order-meta",
      orderNoText,
      orderMetaText,
      hasReadableOrderNo: orderNoText.includes("2026-09-12 · 30FC29B0"),
      hasMaskedPhone: orderMetaText.includes("188****0000"),
      hasRawPhone: orderMetaText.includes("18800000000")
    });
    if (!orderNoText.includes("2026-09-12 · 30FC29B0") || orderNoText.includes("mp_2026")) {
      report.errors.push("订单列表仍展示原始长工程订单号或缺少可读短号");
    }
    if (!orderMetaText.includes("到店自提 · 联系人：张三 · 188****0000") || orderMetaText.includes("18800000000")) {
      report.errors.push("订单列表缺少履约方式、自提联系人标签或手机号未脱敏");
    }
    if (!orderMetaText.includes("预约取货：2026-09-13 15:00")) {
      report.errors.push("订单列表预约取货时间缺少履约语义或格式不完整");
    }
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/final-orders-readable-meta.png");

    await orders.setData({ filteredOrders: [], loading: false, emptyText: "暂无订单" });
    await sleep(180);
    const orderEmptyState = await orders.$(".yunxi-state");
    const orderEmptyTitle = orderEmptyState ? await orderEmptyState.$(".yunxi-state__title") : null;
    const orderEmptyAction = orderEmptyState ? await orderEmptyState.$(".yunxi-state__action") : null;
    const orderEmptyTitleText = orderEmptyTitle ? (await orderEmptyTitle.text()).trim() : "";
    const orderEmptyActionText = orderEmptyAction ? (await orderEmptyAction.text()).trim() : "";
    report.checks.push({
      page: orders.path,
      state: "logged-in-empty-orders",
      orderEmptyTitleText,
      orderEmptyActionText,
      hasEmptyState: Boolean(orderEmptyState),
      hasEmptyAction: Boolean(orderEmptyAction)
    });
    if (
      !orderEmptyState ||
      orderEmptyTitleText !== "暂无订单" ||
      orderEmptyActionText !== "去选购"
    ) {
      report.errors.push("登录后空订单页缺少完整空态或去选购入口");
    }
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/final-orders-empty.png");

    const coupons = await navigateAndWait(miniProgram, "pages/coupons/index");
    await sleep(400);
    await coupons.setData({
      loggedIn: true,
      loading: false,
      loadFailed: false,
      activeTab: "available",
      groups: { available: [], used: [], refunded: [], expired: [] }
    });
    await sleep(220);
    const couponState = await coupons.$(".yunxi-state");
    const couponTitle = couponState ? await couponState.$(".yunxi-state__title") : null;
    const couponAction = couponState ? await couponState.$(".yunxi-state__action") : null;
    const couponTitleText = couponTitle ? (await couponTitle.text()).trim() : "";
    const couponActionText = couponAction ? (await couponAction.text()).trim() : "";
    const couponActionSize = couponAction ? await couponAction.size() : null;
    report.checks.push({
      page: coupons.path,
      state: "logged-in-empty-coupons",
      couponTitleText,
      couponActionText,
      couponActionSize
    });
    if (!couponState || couponTitleText !== "暂无可用优惠券" || couponActionText !== "去选购") {
      report.errors.push("登录后空优惠券页缺少完整空态或去选购入口");
    }
    if (couponActionSize && (couponActionSize.width < 44 || couponActionSize.height < 44)) {
      report.errors.push("优惠券空态动作触控区域小于 44px");
    }
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/final-coupons-empty.png");

    const points = await navigateAndWait(miniProgram, "pages/points/index");
    await sleep(400);
    await points.setData({
      loggedIn: true,
      loading: false,
      loadFailed: false,
      pointsBalance: 0,
      rows: []
    });
    await sleep(220);
    const pointsState = await points.$(".yunxi-state");
    const pointsTitle = pointsState ? await pointsState.$(".yunxi-state__title") : null;
    const pointsAction = pointsState ? await pointsState.$(".yunxi-state__action") : null;
    const pointsTitleText = pointsTitle ? (await pointsTitle.text()).trim() : "";
    const pointsActionText = pointsAction ? (await pointsAction.text()).trim() : "";
    report.checks.push({
      page: points.path,
      state: "logged-in-empty-points",
      pointsTitleText,
      pointsActionText
    });
    if (!pointsState || pointsTitleText !== "暂无积分记录" || pointsActionText !== "去选购") {
      report.errors.push("登录后空积分页缺少完整空态或去选购入口");
    }
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/final-points-empty.png");

    const profile = await navigateAndWait(miniProgram, "pages/profile/index", true);
    const profileData = await profile.data();
    await profile.setData({
      sessionView: {
        ...(profileData.sessionView || {}),
        statusText: "微信身份",
        badgeText: "已登录",
        actionText: "刷新信息",
        hintText: "当前身份可用于查询订单和会员资产",
        loggedIn: true
      },
      memberProps: {
        greeting: "HI",
        name: "张三",
        levelText: "普通会员",
        cardSubtitle: "累计消费升级会员等级",
        cardValidity: "永久有效",
        points: 0,
        coupons: 0,
        balanceFen: 0,
        benefitCardCount: 0
      },
      assetBalanceFen: 0,
      assetPoints: 0,
      assetCouponCount: 0,
      balanceText: "¥0.00",
      assetsLoaded: true
    });
    await sleep(300);
    const profileRoot = await profile.$(".page");
    const profileText = profileRoot ? await profileRoot.text() : "";
    const levelBadge = await profile.$(".profile-level-badge");
    const levelBadgeText = levelBadge ? (await levelBadge.text()).trim() : "";
    report.checks.push({
      page: profile.path,
      state: "truthful-member-summary",
      levelBadgeText,
      hasVipCopy: profileText.includes("VIP 会员"),
      hasFakeNumber: profileText.includes("8888 6666"),
      hasAvatarPlaceholder: profileText.includes("👤")
    });
    if (levelBadgeText !== "普通会员") {
      report.errors.push("个人中心会员等级未使用 memberSummary 的真实配置");
    }
    if (profileText.includes("VIP 会员") || profileText.includes("8888 6666") || profileText.includes("👤")) {
      report.errors.push("个人中心仍存在矛盾会员等级、虚假会员编号或占位头像");
    }
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/final-profile-member-summary.png");
  } finally {
    await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);
    await miniProgram.disconnect();
  }

  report.status = finalizeAuditStatus(report);
  fs.mkdirSync("reports/devtools", { recursive: true });
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
  console.log(`Commerce state audit: ${report.status}`);
  console.log(`Report written to: ${REPORT_PATH}`);

  for (const error of report.errors) {
    console.error(`  x ${error}`);
  }
  if (report.blockedReason) {
    console.log(`  ! ${report.blockedReason}`);
  }
  exitForAuditStatus(report.status);
}

main().catch((error) => {
  console.error("Commerce state audit failed:", error);
  process.exit(1);
});
