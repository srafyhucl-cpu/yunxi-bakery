const automator = require("miniprogram-automator");
const fs = require("node:fs");
const {
  captureEvidenceScreenshot,
  finalizeAuditStatus,
  exitForAuditStatus
} = require("./lib/devtools-audit-status.cjs");

const WS_ENDPOINT = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const REPORT_PATH = "reports/devtools/miniapp-commerce-flows.json";
const CART_STORAGE_KEY = "cartItems";
const HOME_ROUTE = "pages/home/index";
const PRODUCTS_ROUTE = "pages/products/index";
const PRODUCT_DETAIL_ROUTE = "pages/product-detail/index";
const CART_ROUTE = "pages/cart/index";
const CHECKOUT_ROUTE = "pages/checkout/index";
const ORDER_DETAIL_ROUTE = "pages/order-detail/index";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function addCheck(report, name, data, passed, error) {
  report.checks.push({ name, passed, ...data });
  if (!passed) {
    report.errors.push(error);
  }
}

// 悬浮栏实底要看不透明度而不是只看 class：class 切换瞬间背景色还在 0.18s 过渡中，
// 直接读样式会拿到 transparent，产生假失败（见 ERRORS M-20260913-130）。
function resolveColorAlpha(color) {
  const parts = (String(color || "").match(/rgba?\(([^)]+)\)/) || [])[1];
  const channels = parts ? parts.split(",").map((part) => Number.parseFloat(part)) : [];
  if (channels.length >= 4) {
    return channels[3];
  }
  return channels.length === 3 ? 1 : 0;
}

function parseRgbaColor(color) {
  const parts = (String(color || "").match(/rgba?\(([^)]+)\)/) || [])[1];
  if (!parts) {
    return null;
  }
  const channels = parts.split(",").map((part) => Number.parseFloat(part));
  if (channels.length < 3 || channels.some((channel) => !Number.isFinite(channel))) {
    return null;
  }
  return {
    r: channels[0],
    g: channels[1],
    b: channels[2],
    a: channels.length >= 4 ? channels[3] : 1
  };
}

function composeOver(foreground, backdrop) {
  return {
    r: foreground.r * foreground.a + backdrop.r * (1 - foreground.a),
    g: foreground.g * foreground.a + backdrop.g * (1 - foreground.a),
    b: foreground.b * foreground.a + backdrop.b * (1 - foreground.a)
  };
}

function relativeLuminance(color) {
  const toLinear = (value) => {
    const channel = value / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * toLinear(color.r) + 0.7152 * toLinear(color.g) + 0.0722 * toLinear(color.b);
}

function contrastRatio(first, second) {
  const firstLuminance = relativeLuminance(first);
  const secondLuminance = relativeLuminance(second);
  const lighter = Math.max(firstLuminance, secondLuminance);
  const darker = Math.min(firstLuminance, secondLuminance);
  return (lighter + 0.05) / (darker + 0.05);
}

// 标题底栅是半透明的，实际底色取决于身后的商品图；
// 按全白与全黑两个边界各算一次并取更差的一侧，避免用“看起来还行”的截图当结论。
function worstCaseTitleContrast(textColor, surfaceColor) {
  const text = parseRgbaColor(textColor);
  const surface = parseRgbaColor(surfaceColor);
  if (!text || !surface) {
    return 0;
  }
  return Math.min(
    contrastRatio(text, composeOver(surface, { r: 255, g: 255, b: 255 })),
    contrastRatio(text, composeOver(surface, { r: 0, g: 0, b: 0 }))
  );
}

async function navigateAndWait(miniProgram, route, isTabPage = false) {
  const expectedRoute = route.split("?")[0];
  if (isTabPage) {
    await miniProgram.switchTab(`/${route}`);
  } else {
    await miniProgram.reLaunch(`/${route}`);
  }

  for (let index = 0; index < 10; index += 1) {
    await sleep(350);
    const page = await miniProgram.currentPage();
    if (page.path === expectedRoute) {
      return page;
    }
  }
  return miniProgram.currentPage();
}

async function waitForValue(readValue, description) {
  for (let index = 0; index < 12; index += 1) {
    const value = await readValue();
    if (value) {
      return value;
    }
    await sleep(350);
  }
  throw new Error(`等待${description}超时`);
}

async function readSubmitState(page) {
  const data = await page.data();
  const submit = await page.$(".checkout-footer__submit");
  const guidanceTitle = await page.$(".delivery-guidance__title");
  return {
    deliveryType: data.deliveryType,
    deliveryQuoteStatus: data.deliveryQuoteStatus,
    deliveryQuoteId: data.deliveryQuoteId,
    deliveryFeeFen: data.deliveryFeeFen,
    deliveryFeeText: data.deliveryFeeText,
    canSubmitOrder: data.canSubmitOrder,
    submitButtonText: data.submitButtonText,
    submitDisabled: submit ? Boolean(await submit.property("disabled")) : null,
    guidanceTitle: guidanceTitle ? (await guidanceTitle.text()).trim() : "",
  };
}

async function readScheduleState(page) {
  const data = await page.data();
  const preview = await page.$(".time-preview");
  const expectTime = String(data.expectTime || "").trim();
  const match = expectTime.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})$/);
  return {
    expectTime,
    previewText: preview ? (await preview.text()).trim() : "",
    selectedDateValue: String(data.selectedDateValue || ""),
    selectedHourValue: data.hourOptions?.[data.selectedHourIndex] || "",
    selectedMinuteValue: data.minuteOptions?.[data.selectedMinuteIndex] || "",
    expectedDateValue: match ? match[1] : "",
    expectedHourValue: match ? String(Number(match[2])).padStart(2, "0") : "",
    expectedMinuteValue: match ? match[3] : "",
  };
}

// 顶部购买卡、费用明细和底栏各自有金额文案，必须同时读取，才能发现“小计已刷新、实付仍停在旧值”这类不一致。
async function readCheckoutAmountState(page) {
  const data = await page.data();
  const summaryHint = await page.$(".checkout-summary__hint");
  const summaryTotal = await page.$(".checkout-total");
  const footerAmount = await page.$(".checkout-footer__amount");
  const footerNote = await page.$(".checkout-footer__note");
  const breakdown = {};
  for (const row of await page.$$(".amount-row")) {
    const cells = [];
    for (const cell of await row.$$("text")) {
      cells.push((await cell.text()).trim());
    }
    if (cells.length >= 2) {
      breakdown[cells[0]] = cells[cells.length - 1];
    }
  }
  return {
    summaryHint: summaryHint ? (await summaryHint.text()).trim() : "",
    summaryTotal: summaryTotal ? (await summaryTotal.text()).trim() : "",
    footerAmount: footerAmount ? (await footerAmount.text()).trim() : "",
    footerNote: footerNote ? (await footerNote.text()).trim() : "",
    totalText: String(data.totalText || ""),
    goodsFenText: String(data.goodsFenText || ""),
    estimateRemainFenText: String(data.estimateRemainFenText || ""),
    breakdown,
  };
}

async function applyCheckoutState(page, state) {
  await page.setData({
    isLoggedIn: true,
    loginStateText: "已使用本地审计态加载结算信息",
    errorMessage: "",
    checkoutItems: [
      {
        productId: "commerce-flow-audit-item",
        title: "商品优先流程审计样本",
        imageUrl: "",
        priceFen: 19800,
        priceText: "¥198.00",
        quantity: 1,
      },
    ],
    receiverName: state.deliveryType === "delivery" ? "流程审计" : "",
    receiverPhone: state.deliveryType === "delivery" ? "18800000001" : "",
    deliveryType: state.deliveryType,
    deliveryAddress: state.deliveryType === "delivery" ? "北京市朝阳区测试路 1 号" : "",
    selectedAddressText: state.deliveryType === "delivery" ? "流程审计 18800000001" : "",
    goodsFen: 19800,
    goodsFenText: "¥198.00",
    estimateRemainFenText: state.estimateRemainFenText,
    deliveryFeeFen: state.deliveryFeeFen,
    deliveryFeeText: state.deliveryFeeText,
    deliveryQuoteId: state.deliveryQuoteId,
    deliveryQuoteStatus: state.deliveryQuoteStatus,
    deliveryCalculating: state.deliveryCalculating,
    agreementAccepted: true,
    pendingBarVisible: false,
    submitting: false,
  });
  await page.callMethod("syncExpectTimeSchedule");
  // 注入态同样要走页面自身的金额重算，否则顶部小计/底栏说明会停在旧值（见 ERRORS M-20260918-004）。
  await page.callMethod("refreshEstimate");
  await page.callMethod("refreshSubmitState");
  await sleep(160);
}

async function main() {
  const report = {
    generatedAt: new Date().toISOString(),
    mode: "readonly-and-state-injected",
    status: "FAIL",
    checks: [],
    errors: [],
  };
  let miniProgram;

  try {
    miniProgram = await automator.connect({ wsEndpoint: WS_ENDPOINT });
    await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);

    const home = await navigateAndWait(miniProgram, HOME_ROUTE, true);
    const homeProduct = await waitForValue(async () => {
      const data = await home.data();
      const products = (data.blocks || []).flatMap((block) => block.products || []);
      return products.find((product) => product.id) || null;
    }, "首页精选商品");
    const homeCard = await home.$(".shelf .product-card");
    addCheck(
      report,
      "home-featured",
      { route: home.path, productId: homeProduct.id, title: homeProduct.title, hasCard: Boolean(homeCard) },
      home.path === HOME_ROUTE && Boolean(homeCard),
      "首页未优先展示可点击精选商品货架"
    );
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/commerce-flow-home.png");

    const catalog = await navigateAndWait(miniProgram, PRODUCTS_ROUTE, true);
    const catalogData = await waitForValue(async () => {
      const data = await catalog.data();
      if (Array.isArray(data.activeProducts) && data.activeProducts.length > 0) {
        return data;
      }
      // 上一轮审计可能留下空分类或搜索态：页面已加载却没有商品时，走页面自身的重载入口。
      if (data.loaded === true && data.loading !== true) {
        await catalog.callMethod("retryLoad");
      }
      return null;
    }, "商品列表");
    const soldNumbers = (catalogData.activeProducts || [])
      .map((product) => {
        const match = /^已售\s*(\d+)$/.exec(String(product.soldText || "").trim());
        return match ? Number(match[1]) : null;
      })
      .filter((value) => value !== null);
    const isPopularOrdered = soldNumbers.every(
      (value, index) => index === 0 || soldNumbers[index - 1] >= value
    );
    addCheck(
      report,
      "product-list",
      {
        route: catalog.path,
        productCount: Number(catalogData.catalogTotal || 0),
        visibleCount: catalogData.activeProducts.length,
        soldNumbers,
        isPopularOrdered,
      },
      catalog.path === PRODUCTS_ROUTE && catalogData.activeProducts.length > 0 && isPopularOrdered,
      "商品列表未渲染或未按真实销量降序"
    );
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/commerce-flow-products.png");

    const detailProductId = catalogData.activeProducts.some((product) => product.id === "3610295088")
      ? "3610295088"
      : catalogData.activeProducts[0].id;
    const detail = await navigateAndWait(
      miniProgram,
      `${PRODUCT_DETAIL_ROUTE}?id=${encodeURIComponent(detailProductId)}`
    );
    const detailData = await waitForValue(async () => {
      const data = await detail.data();
      return data.product ? data : null;
    }, "商品详情直达");
    const detailPayload = JSON.stringify({
      title: detailData.product.title,
      subtitle: detailData.product.displaySubtitle,
      description: detailData.product.description,
      tags: detailData.product.tags,
      specs: detailData.product.specs,
    });
    const hasImportNoise = /(商品名称|在售状态|当前可用库存|h5\.youzan\.com|\[UMP)/.test(
      detailPayload
    );
    const fulfillmentCard = await detail.$(".detail-fulfillment-card");
    addCheck(
      report,
      "product-detail-direct",
      {
        route: detail.path,
        productId: detailData.product.id,
        title: detailData.product.title,
        fulfillmentHint: detailData.product.displayFulfillment,
        hasImportNoise,
        hasFulfillmentCard: Boolean(fulfillmentCard),
      },
      detail.path === PRODUCT_DETAIL_ROUTE &&
        !hasImportNoise &&
        Boolean(detailData.product.displayFulfillment) &&
        Boolean(fulfillmentCard),
      "商品详情直达存在同步噪声或缺少履约说明"
    );
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/commerce-flow-detail.png");

    // 商品详情滚动后悬浮栏必须切实底，否则正文会穿透到状态栏与返回控件下方。
    const detailScroll = await detail.$(".page-scroll");
    const detailNav = await detail.$(".detail-nav");
    const initialNavClass = detailNav ? (await detailNav.attribute("class")) || "" : "";
    const detailNavTitle = await detail.$(".detail-nav .page-fixed-safe__title");
    const initialTitleColor = detailNavTitle ? await detailNavTitle.style("color") : "";
    const initialTitleBackground = detailNavTitle
      ? await detailNavTitle.style("background-color")
      : "";
    let scrolledNavClass = "";
    let scrolledNavBackground = "";
    let scrolledTitleBackground = "";
    let restoredNavClass = "";
    let restoredTitleBackground = "";
    if (detailScroll && detailNav) {
      await detailScroll.scrollTo(0, 240);
      for (let index = 0; index < 12; index += 1) {
        scrolledNavClass = (await detailNav.attribute("class")) || "";
        scrolledNavBackground = await detailNav.style("background-color");
        if (detailNavTitle) {
          scrolledTitleBackground = await detailNavTitle.style("background-color");
        }
        if (scrolledNavClass.includes("detail-nav--solid") && resolveColorAlpha(scrolledNavBackground) >= 0.9) {
          break;
        }
        await sleep(300);
      }
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/commerce-flow-detail-nav-solid.png");
      await detailScroll.scrollTo(0, 0);
      for (let index = 0; index < 12; index += 1) {
        restoredNavClass = (await detailNav.attribute("class")) || "";
        const restoredNavBackground = await detailNav.style("background-color");
        if (detailNavTitle) {
          restoredTitleBackground = await detailNavTitle.style("background-color");
        }
        if (!restoredNavClass.includes("detail-nav--solid") && resolveColorAlpha(restoredNavBackground) < 0.1) {
          break;
        }
        await sleep(300);
      }
    }
    const solidNavAlpha = resolveColorAlpha(scrolledNavBackground);
    addCheck(
      report,
      "product-detail-scroll-nav",
      {
        route: detail.path,
        initialNavClass,
        scrolledNavClass,
        scrolledNavBackground,
        restoredNavClass,
      },
      Boolean(detailScroll) &&
        Boolean(detailNav) &&
        !initialNavClass.includes("detail-nav--solid") &&
        scrolledNavClass.includes("detail-nav--solid") &&
        solidNavAlpha >= 0.9 &&
        !restoredNavClass.includes("detail-nav--solid"),
      "商品详情滚动后悬浮栏未切实底，正文会穿透到状态栏与返回控件下方"
    );

    // 沉浸态标题必须自带底衬：商家上传的商品图明暗不可控，深色标题直接压图会不可读。
    const immersiveTitleSurfaceAlpha = resolveColorAlpha(initialTitleBackground);
    const immersiveTitleContrast = worstCaseTitleContrast(initialTitleColor, initialTitleBackground);
    addCheck(
      report,
      "product-detail-immersive-title-contrast",
      {
        route: detail.path,
        titleColor: initialTitleColor,
        titleBackground: initialTitleBackground,
        worstCaseContrast: Number(immersiveTitleContrast.toFixed(2)),
        solidTitleBackground: scrolledTitleBackground,
        restoredTitleBackground
      },
      Boolean(detailNavTitle) &&
        immersiveTitleSurfaceAlpha >= 0.8 &&
        immersiveTitleContrast >= 4.5 &&
        resolveColorAlpha(scrolledTitleBackground) < 0.1 &&
        resolveColorAlpha(restoredTitleBackground) >= 0.8,
      "商品详情沉浸态标题缺少足够对比度底衬，或滚动实底后未复位标题底衬"
    );

    await miniProgram.callWxMethod("setStorageSync", CART_STORAGE_KEY, [
      {
        productId: "commerce-flow-audit-item",
        title: "商品优先流程审计样本",
        imageUrl: "",
        priceFen: 19800,
        quantity: 1,
        stock: 8,
      },
    ]);
    const cart = await navigateAndWait(miniProgram, CART_ROUTE, true);
    const cartData = await waitForValue(async () => {
      const data = await cart.data();
      return data.hasItems ? data : null;
    }, "购物车商品");
    const cartItem = await cart.$(".cart-item");
    const cartFooter = await cart.$(".cart-footer");
    addCheck(
      report,
      "cart",
      {
        route: cart.path,
        itemCount: cartData.items.length,
        totalText: cartData.totalText,
        hasItem: Boolean(cartItem),
        hasFooter: Boolean(cartFooter),
      },
      cart.path === CART_ROUTE && Boolean(cartItem) && Boolean(cartFooter),
      "购物车缺少商品行或结算栏"
    );
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/commerce-flow-cart.png");

    const checkout = await navigateAndWait(miniProgram, CHECKOUT_ROUTE);
    if (checkout.path !== CHECKOUT_ROUTE) {
      throw new Error(`结算页路由错误：${checkout.path}`);
    }
    await applyCheckoutState(checkout, {
      deliveryType: "pickup",
      deliveryQuoteStatus: "not_applicable",
      deliveryQuoteId: "",
      deliveryFeeFen: 0,
      deliveryFeeText: "免运费",
      deliveryCalculating: false,
      estimateRemainFenText: "¥198.00",
    });
    const pickupState = await readSubmitState(checkout);
    addCheck(
      report,
      "checkout-pickup",
      pickupState,
      pickupState.canSubmitOrder === true &&
        pickupState.submitDisabled === false &&
        pickupState.deliveryFeeFen === 0,
      "门店自提结算未按免配送费进入可提交态"
    );
    const pickupAmounts = await readCheckoutAmountState(checkout);
    addCheck(
      report,
      "checkout-pickup-amounts",
      pickupAmounts,
      pickupAmounts.summaryHint.includes("商品小计") &&
        pickupAmounts.summaryTotal === "¥198.00" &&
        pickupAmounts.totalText === "¥198.00" &&
        pickupAmounts.footerAmount === "¥198.00" &&
        pickupAmounts.footerNote === "自提价 · 免运费" &&
        pickupAmounts.breakdown["商品金额"] === "¥198.00" &&
        pickupAmounts.breakdown["实付（估算）"] === "¥198.00",
      "自提结算的顶部商品小计、费用明细与底栏实付金额不一致"
    );

    await applyCheckoutState(checkout, {
      deliveryType: "delivery",
      deliveryQuoteStatus: "quoted",
      deliveryQuoteId: "quote-ui-audit",
      deliveryFeeFen: 2600,
      deliveryFeeText: "¥26.00",
      deliveryCalculating: false,
      estimateRemainFenText: "¥224.00",
    });
    const quotedState = await readSubmitState(checkout);
    addCheck(
      report,
      "checkout-delivery-quoted",
      quotedState,
      quotedState.canSubmitOrder === true &&
        quotedState.submitDisabled === false &&
        quotedState.deliveryQuoteId === "quote-ui-audit" &&
        quotedState.deliveryFeeFen === 2600,
      "闪送已报价态未携带有效报价并进入可提交态"
    );
    const quotedAmounts = await readCheckoutAmountState(checkout);
    addCheck(
      report,
      "checkout-delivery-amounts",
      quotedAmounts,
      quotedAmounts.summaryHint.includes("商品小计") &&
        quotedAmounts.summaryTotal === "¥198.00" &&
        quotedAmounts.totalText === "¥198.00" &&
        quotedAmounts.breakdown["商品金额"] === "¥198.00" &&
        quotedAmounts.breakdown["闪送运费"] === "¥26.00" &&
        quotedAmounts.breakdown["实付（估算）"] === "¥224.00" &&
        quotedAmounts.footerAmount === "¥224.00" &&
        quotedAmounts.footerNote === "已含闪送费 ¥26.00",
      "闪送已报价结算的顶部商品小计、费用明细与底栏实付金额不一致"
    );
    const scheduleState = await readScheduleState(checkout);
    addCheck(
      report,
      "checkout-schedule-consistency",
      scheduleState,
      Boolean(scheduleState.expectedDateValue) &&
        scheduleState.previewText.includes(scheduleState.expectTime) &&
        scheduleState.selectedDateValue === scheduleState.expectedDateValue &&
        scheduleState.selectedHourValue === scheduleState.expectedHourValue &&
        scheduleState.selectedMinuteValue === scheduleState.expectedMinuteValue,
      "结算页日期/时分控件与期望时间预览不一致"
    );
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/commerce-flow-checkout-quoted.png");

    await applyCheckoutState(checkout, {
      deliveryType: "delivery",
      deliveryQuoteStatus: "expired",
      deliveryQuoteId: "",
      deliveryFeeFen: 0,
      deliveryFeeText: "报价已过期",
      deliveryCalculating: false,
      estimateRemainFenText: "¥198.00",
    });
    const expiredState = await readSubmitState(checkout);
    addCheck(
      report,
      "checkout-delivery-expired",
      expiredState,
      expiredState.canSubmitOrder === false &&
        expiredState.submitDisabled === true &&
        expiredState.guidanceTitle === "闪送报价已过期",
      "闪送报价过期后仍允许提交或缺少重新确认指引"
    );

    await applyCheckoutState(checkout, {
      deliveryType: "delivery",
      deliveryQuoteStatus: "address_out_of_range",
      deliveryQuoteId: "",
      deliveryFeeFen: 0,
      deliveryFeeText: "当前地址超出配送范围",
      deliveryCalculating: false,
      estimateRemainFenText: "¥198.00",
    });
    const outOfRangeState = await readSubmitState(checkout);
    addCheck(
      report,
      "checkout-delivery-out-of-range",
      outOfRangeState,
      outOfRangeState.canSubmitOrder === false &&
        outOfRangeState.submitDisabled === true &&
        outOfRangeState.guidanceTitle === "当前地址暂不支持闪送",
      "超范围地址仍允许按零运费提交或缺少替代履约指引"
    );

    const orderDetail = await navigateAndWait(miniProgram, ORDER_DETAIL_ROUTE);
    await sleep(500);
    await orderDetail.setData({
      loading: false,
      canLoadOrder: true,
      order: {
        id: "UI-AUDIT-ORDER",
        status: "preparing",
        statusText: "制作中",
        paymentStatusText: "已支付",
        progressText: "门店正在制作，完成后会交接闪送配送。",
        progressSteps: [
          {
            status: "paid",
            title: "已支付",
            description: "订单金额已确认",
            timeText: "2026-09-12 10:00",
            note: "",
            state: "done",
          },
          {
            status: "preparing",
            title: "制作中",
            description: "门店正在制作商品",
            timeText: "2026-09-12 10:30",
            note: "",
            state: "current",
          },
        ],
        createdAt: "2026-09-12 10:00",
        updatedAt: "2026-09-12 10:30",
        paymentMethodText: "门店确认",
        itemsView: [
          {
            productId: "commerce-flow-audit-item",
            title: "商品优先流程审计样本",
            quantity: 1,
            priceText: "¥198.00",
            subtotalText: "¥198.00",
          },
        ],
        goodsTotalText: "¥198.00",
        deliveryFeeText: "¥26.00",
        hasDeliveryFee: true,
        totalText: "¥224.00",
        deliveryTypeText: "北京闪送",
        receiverLabel: "收货人",
        expectTimeLabel: "期望配送",
        receiverName: "流程审计",
        receiverPhone: "18800000001",
        expectTime: "2026-09-15 15:00",
        pickupAddress: "北京市东城区南竹杆胡同2号银河SOHO",
        deliveryAddress: "北京市朝阳区测试路 1 号",
        canPay: false,
        canCancel: false,
      },
    });
    await sleep(180);
    const orderStatus = await orderDetail.$(".order-status");
    const orderDetailRoot = await orderDetail.$(".order-detail-page");
    const orderDetailText = orderDetailRoot ? (await orderDetailRoot.text()).trim() : "";
    const orderActions = await orderDetail.$(".order-actions");
    const deliveryFeeRow = await orderDetail.$(".order-total-row--delivery");
    const deliveryAddressRow = await orderDetail.$(".order-row--delivery-address");
    const deliveryAddressText = deliveryAddressRow
      ? (await deliveryAddressRow.text()).trim()
      : "";
    addCheck(
      report,
      "order-detail",
      {
        route: orderDetail.path,
        statusText: orderStatus ? (await orderStatus.text()).trim() : "",
        hasDeliveryFeeRow: Boolean(deliveryFeeRow),
        hasDeliveryAddress: Boolean(deliveryAddressRow),
        deliveryAddressText,
        paymentMethodText: orderDetailText.includes("门店确认") ? "门店确认" : "",
        hasActions: Boolean(orderActions),
      },
      orderDetail.path === ORDER_DETAIL_ROUTE &&
        Boolean(orderStatus) &&
        (await orderStatus.text()).trim() === "制作中" &&
        orderDetailText.includes("门店确认") &&
        !orderDetailText.includes("MVP") &&
        !orderDetailText.includes("模拟支付") &&
        Boolean(deliveryFeeRow) &&
        deliveryAddressText.includes("配送地址") &&
        deliveryAddressText.includes("北京市朝阳区测试路 1 号") &&
        Boolean(orderActions),
      "闪送订单详情未渲染顾客可理解的支付方式、制作状态、闪送费、配送地址或操作区"
    );
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/commerce-flow-order-detail.png");

    await orderDetail.setData({
      loading: false,
      canLoadOrder: true,
      order: {
        ...(await orderDetail.data()).order,
        statusText: "制作中",
        progressText: "门店正在制作，完成后会进入待取货状态。",
        hasDeliveryFee: false,
        deliveryFeeText: "¥0.00",
        totalText: "¥198.00",
        deliveryTypeText: "到店自提",
        receiverLabel: "联系人",
        expectTimeLabel: "预约取货",
        pickupAddress: "北京市东城区南竹杆胡同2号银河SOHO",
        deliveryAddress: "",
        progressSteps: [
          {
            status: "paid",
            title: "已支付",
            description: "订单金额已确认",
            timeText: "2026-09-12 10:00",
            note: "",
            state: "done",
          },
          {
            status: "making",
            title: "制作中",
            description: "门店正在制作商品",
            timeText: "2026-09-12 10:30",
            note: "",
            state: "current",
          },
          {
            status: "delivering",
            title: "待取货",
            description: "商品已备好，请按预约时间到店取货",
            timeText: "",
            note: "",
            state: "todo",
          },
        ],
      },
    });
    await sleep(180);
    const pickupDetailCard = await orderDetail.$(".order-detail-page");
    const pickupDetailText = pickupDetailCard ? (await pickupDetailCard.text()).trim() : "";
    const pickupAddressRow = await orderDetail.$(".order-row--pickup-address");
    const pickupAddressText = pickupAddressRow ? (await pickupAddressRow.text()).trim() : "";
    addCheck(
      report,
      "order-detail-pickup",
      {
        route: orderDetail.path,
        hasDeliveryFeeRow: Boolean(await orderDetail.$(".order-total-row--delivery")),
        hasPickupAddress: Boolean(pickupAddressRow),
        pickupAddressText,
        hasPickupProgress: pickupDetailText.includes("待取货"),
      },
      orderDetail.path === ORDER_DETAIL_ROUTE &&
        !(await orderDetail.$(".order-total-row--delivery")) &&
        pickupAddressText.includes("自提门店") &&
        pickupAddressText.includes("北京市东城区南竹杆胡同2号银河SOHO") &&
        pickupDetailText.includes("联系人") &&
        pickupDetailText.includes("预约取货") &&
        pickupDetailText.includes("待取货"),
      "自提订单详情仍展示闪送费、缺少门店地址、履约标签或待取货进度"
    );
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/commerce-flow-order-detail-pickup.png");

    report.status = report.errors.length === 0 ? "PASS" : "FAIL";
  } catch (error) {
    report.errors.push(error instanceof Error ? error.message : String(error));
  } finally {
    if (miniProgram) {
      try {
        await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);
      } catch (error) {
        report.errors.push(
          `购物车清理失败：${error instanceof Error ? error.message : String(error)}`
        );
      }
      await miniProgram.disconnect();
    }
    fs.mkdirSync("reports/devtools", { recursive: true });
    report.status = finalizeAuditStatus(report);
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
  }

  console.log(`Miniapp commerce flows: ${report.status}`);
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
