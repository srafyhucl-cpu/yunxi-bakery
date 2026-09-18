const automator = require("d:/Project/YunxiBakery/miniapp/node_modules/miniprogram-automator");
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const {
  BLOCKED_REASON,
  captureScreenshotWithRetry,
} = require("./lib/devtools-audit-status.cjs");

const WS_ENDPOINT = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const reportsDir = "d:/Project/YunxiBakery/miniapp/reports/devtools";
const PROBE_TIMEOUT_MS = Number.parseInt(process.env.MINIAPP_AUTOMATOR_TIMEOUT_MS || "20000", 10);
const AUTH_STORAGE_KEYS = ["miniappSession", "miniappUserId"];

const MINIAPP_API_BASE = process.env.MINIAPP_API_BASE || "http://127.0.0.1:7001";

// 商品详情必须用真实商品 ID 取证；空态截图不能冒充商品详情视觉证据。
let productDetailQueryId = "";

// 截图是否可用只按每次调用的真实结果判定：进程名不能证明桌面可截图（M-20260913-143）。

// 首页货架期望条数取自真实接口，用于捕捉缓存键缺 limit 导致的条数漂移。
async function fetchHomeShelfLimitCount(limit) {
  try {
    const response = await fetch(`${MINIAPP_API_BASE}/api/v1/miniapp/products?featured=true&limit=${limit}`);
    if (!response.ok) {
      return null;
    }
    const payload = await response.json();
    return Array.isArray(payload?.data) ? payload.data.length : null;
  } catch (error) {
    console.warn(`首页货架接口不可用，跳过条数交叉校验：${error instanceof Error ? error.message : String(error)}`);
    return null;
  }
}

// 取一个真实在售商品作为详情页取证样本，避免 reLaunch 无参导致“商品不存在”空态。
async function fetchFirstCatalogProductId() {
  try {
    const response = await fetch(`${MINIAPP_API_BASE}/api/v1/miniapp/products?limit=8&sort=popular`);
    if (!response.ok) {
      return "";
    }
    const payload = await response.json();
    const products = Array.isArray(payload?.data) ? payload.data : [];
    const target = products.find(
      (product) => product && product.id && product.imageUrl && product.stock > 0 && product.isActive !== false
    );
    return target ? String(target.id) : "";
  } catch (error) {
    console.warn(`商品详情取证样本接口不可用：${error instanceof Error ? error.message : String(error)}`);
    return "";
  }
}

const TAB_BAR_PAGES = new Set([
  "pages/home/index",
  "pages/products/index",
  "pages/cart/index",
  "pages/chat/index",
  "pages/profile/index",
]);

const ALL_15_PAGES = [
  { path: "pages/home/index", type: "tab", title: "芸熙烘焙" },
  { path: "pages/products/index", type: "tab", title: "全部商品" },
  { path: "pages/cart/index", type: "tab", title: "购物车" },
  { path: "pages/chat/index", type: "tab", title: "客服顾问" },
  { path: "pages/profile/index", type: "tab", title: "会员中心" },
  { path: "pages/orders/index", type: "sub", title: "我的订单" },
  { path: "pages/order-detail/index", type: "sub", title: "订单详情" },
  { path: "pages/coupons/index", type: "sub", title: "我的优惠券" },
  { path: "pages/points/index", type: "sub", title: "积分明细" },
  { path: "pages/recharge/index", type: "sub", title: "余额充值" },
  { path: "pages/address/index", type: "sub", title: "收货地址" },
  { path: "pages/checkout/index", type: "sub", title: "确认订单" },
  { path: "pages/product-detail/index", type: "sub", title: "商品详情" },
  { path: "pages/policy/index", type: "sub", title: "服务协议" },
  { path: "pages/group-registration/index", type: "sub", title: "群内登记" },
];

// 未登录访问受限页面时，统一使用登录引导空态，而不是只留一条会话提示加大片空白。
const LOGIN_GATE_PAGES = [
  "pages/orders/index",
  "pages/address/index",
  "pages/order-detail/index",
  "pages/coupons/index",
  "pages/points/index",
  "pages/recharge/index",
  "pages/checkout/index",
];

// 登录引导态下不得同时泄露受限业务内容。
const LOGIN_GATE_LIMITED_CONTENT = {
  "pages/orders/index": [".filter-tabs-bar", ".order-list"],
  "pages/address/index": [".address-header", ".address-form", ".address-add"],
  "pages/order-detail/index": [".order-card"],
  "pages/coupons/index": [".coupon-tabs", ".coupon-list"],
  "pages/points/index": [".balance-panel", ".ledger-list"],
  "pages/recharge/index": [".tier-panel", ".balance-panel"],
  "pages/checkout/index": [".form", ".checkout-footer"],
};

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// 滚动状态由小程序端事件驱动，DevTools 下渲染存在延迟；轮询到目标状态再断言，避免假失败。
async function waitForDetailNavBackground(nav, expectOpaque, budgetMs = 3000) {
  // 背景带 0.18s 过渡，DevTools 计算样式刷新还会滞后；只轮询到稳定值，避免把过渡期读成透明。
  const deadline = Date.now() + budgetMs;
  let background = "";
  for (;;) {
    background = await nav.style("background-color");
    const color = parseCssColor(background);
    const opaque = Boolean(color) && color.a >= 0.9;
    if (opaque === expectOpaque || Date.now() >= deadline) {
      return background;
    }
    await sleep(150);
  }
}

async function waitForDetailNavState(nav, expectSolid, budgetMs = 3000) {
  const deadline = Date.now() + budgetMs;
  let className = "";
  let background = "";
  for (;;) {
    className = (await nav.attribute("class")) || "";
    background = await nav.style("background-color");
    if (className.includes("detail-nav--solid") === expectSolid || Date.now() >= deadline) {
      return { className, background };
    }
    await sleep(200);
  }
}

// 锁屏、开发者工具 IDE 卡死、自动化端口未开都会让整轮审计假失败。
// 只按进程名判断会误伤（LogonUI 常驻但桌面可用），因此改为直接探测自动化是否真的响应。
function timeoutAfter(ms, label) {
  let timer;
  const promise = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label}超时（${ms}ms）`)), ms);
  });
  if (typeof timer.unref === "function") {
    timer.unref();
  }
  return promise;
}

// 本地后端是商品、会话与订单运行态断言的依赖；缺服务时只记环境阻塞，不覆盖上一份有效报告。
async function probeBackendHealth() {
  try {
    const response = await fetch(`${MINIAPP_API_BASE}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

// 锁屏期间 WebSocket 仍可能建连成功，但协议命令不返回；两段式探测把这种状态与页面渲染异常区分开。
async function connectWithProbe() {
  const miniProgram = await Promise.race([
    automator.connect({ wsEndpoint: WS_ENDPOINT }),
    timeoutAfter(PROBE_TIMEOUT_MS, "自动化建连"),
  ]);
  await Promise.race([
    miniProgram.currentPage(),
    timeoutAfter(PROBE_TIMEOUT_MS, "自动化响应探测"),
  ]);
  return miniProgram;
}

// 探测失败时补充环境线索；命中登录界面进程才提示解锁，避免把线索当成判定依据。
function describeEnvironmentHint() {
  return isDesktopLocked() ? "，且检测到登录界面进程（可能处于锁屏）" : "";
}

// 锁屏时页面协议仍可响应，但 DevTools 截图接口会失败；截图属于证据，不等同于页面缺陷。
function isDesktopLocked() {
  if (process.platform !== "win32") {
    return false;
  }
  try {
    const output = execFileSync(
      "powershell.exe",
      [
        "-NoProfile",
        "-Command",
        "(Get-Process LogonUI,LockApp -ErrorAction SilentlyContinue | Measure-Object).Count",
      ],
      { encoding: "utf8", timeout: 15000 }
    );
    return Number(String(output).trim()) > 0;
  } catch (err) {
    console.log(`锁屏状态检测失败：${err.message}`);
    return false;
  }
}

async function navigateAndWait(miniProgram, pageDef) {
  const query = pageDef.path === "pages/product-detail/index" && productDetailQueryId
    ? `?id=${encodeURIComponent(productDetailQueryId)}`
    : "";
  const url = `/${pageDef.path}${query}`;
  for (let attempt = 0; attempt < 3; attempt++) {
    if (TAB_BAR_PAGES.has(pageDef.path)) {
      // 首页实例会保留启动时的数据；后端不可用时页面曾回落到 mock 货架，switchTab 会一直复用旧实例。
      // 审计必须重置首页实例，确保截图和条数断言来自当次健康后端，而不是历史 mock 数据。
      if (pageDef.path === "pages/home/index") {
        await miniProgram.reLaunch(url);
      } else {
        await miniProgram.switchTab(url);
      }
    } else {
      await miniProgram.reLaunch(url);
    }
    for (let check = 0; check < 5; check++) {
      await sleep(400);
      const currentPage = await miniProgram.currentPage();
      if (currentPage.path === pageDef.path) {
        return currentPage;
      }
    }
  }
  return miniProgram.currentPage();
}

// 截图必须反映页面默认状态：商品页先清搜索残留，详情页必须命中真实商品，避免拿非默认态或空态当视觉证据。
async function preparePageState(miniProgram, page, pageDef, result) {
  if (pageDef.path === "pages/products/index") {
    let data = await page.data();
    const hadSearch = typeof data.searchText === "string" && data.searchText.trim().length > 0;
    if (hadSearch) {
      await page.callMethod("resetSearchState");
      await sleep(400);
    }
    data = await page.data();
    if (!data.loaded || !Array.isArray(data.activeProducts) || data.activeProducts.length === 0) {
      if (typeof page.callMethod === "function") {
        await page.callMethod("retryLoad");
        await sleep(900);
      }
    }
    const normalized = await page.data();
    const searchText = typeof normalized.searchText === "string" ? normalized.searchText.trim() : "";
    const productCount = Array.isArray(normalized.activeProducts) ? normalized.activeProducts.length : 0;
    result.defaultState = {
      searchText,
      productCount,
      catalogTotal: normalized.catalogTotal,
      clearedSearchResidue: hadSearch,
    };
    if (searchText) {
      result.errors.push(`商品页默认态截图仍带搜索词：${searchText}`);
    }
    if (productCount === 0) {
      result.errors.push("商品页默认态未渲染商品列表");
    }
    // 商品页滚动区是原生页面滚动，元素没有 scrollTo，需要回落到 wx.pageScrollTo。
    const scrollView = await page.$(".page-scroll");
    if (scrollView && typeof scrollView.scrollTo === "function") {
      await scrollView.scrollTo(0, 0);
    } else {
      try {
        await miniProgram.callWxMethod("pageScrollTo", { scrollTop: 0, duration: 0 });
      } catch (error) {
        result.errors.push(
          `商品页滚动复位失败：${error instanceof Error ? error.message : String(error)}`
        );
      }
    }
    await sleep(220);
  }

  if (pageDef.path === "pages/product-detail/index") {
    let data = await page.data();
    for (let attempt = 0; attempt < 15 && !data.product; attempt++) {
      await sleep(300);
      data = await page.data();
    }
    if (!productDetailQueryId) {
      result.defaultState = { skipped: "商品目录为空，未取到真实商品 ID" };
      return;
    }
    result.defaultState = data.product
      ? { productId: data.product.id, title: data.product.title, canPurchase: data.canPurchase }
      : { productId: productDetailQueryId, error: "商品详情未渲染真实商品" };
    if (!data.product) {
      result.errors.push(`商品详情页未能按真实商品 ID 渲染商品：${productDetailQueryId}`);
    }
  }
}

async function readHomeImageFailed(page, collectionKey, blockIndex, itemIndex) {
  const data = await page.data();
  return data.blocks?.[blockIndex]?.[collectionKey]?.[itemIndex]?.imageFailed === true;
}

async function waitForHomeImageFailure(page, collectionKey, blockIndex, itemIndex) {
  for (let attempt = 0; attempt < 30; attempt++) {
    await sleep(200);
    if (await readHomeImageFailed(page, collectionKey, blockIndex, itemIndex)) {
      return true;
    }
  }
  return false;
}

// 首页图片降级验证：触发真实失败回调，确认占位渲染且货架高度不跳动。
async function inspectHomeImageFallback(page, result) {
  const audit = { ok: true, details: [], errors: [] };
  result.homeImageFallback = audit;
  const shelf = await page.$(".shelf");
  const shelfBefore = shelf ? await shelf.size() : null;
  const fallbackBefore = await page.$$(".shelf .product-card .yunxi-image-fallback");
  const data = await page.data();
  const blocks = Array.isArray(data.blocks) ? data.blocks : [];
  const brokenImageUrl = "https://yunxi.invalid/miniapp-image-fallback.png";
  let productTarget = null;
  let heroTarget = null;
  blocks.forEach((block, blockIndex) => {
    (block.products || []).forEach((product, productIndex) => {
      if (!productTarget && product.imageUrl && !product.imageFailed) {
        productTarget = { blockIndex, productIndex, id: product.id, imageUrl: product.imageUrl };
      }
    });
    (block.heroItems || []).forEach((slide, slideIndex) => {
      if (!heroTarget) {
        heroTarget = { blockIndex, slideIndex, id: slide.id, imageUrl: slide.imageUrl };
      }
    });
  });

  if (productTarget) {
    const productPath = `blocks[${productTarget.blockIndex}].products[${productTarget.productIndex}]`;
    await page.setData({
      [`${productPath}.imageUrl`]: brokenImageUrl,
      [`${productPath}.imageFailed`]: false,
    });
    let failed = await waitForHomeImageFailure(page, "products", productTarget.blockIndex, productTarget.productIndex);
    let trigger = "真实 binderror 事件";
    if (!failed) {
      trigger = "直接调用失败回调（真实事件未在 6s 内触发）";
      await page.callMethod("onHomeProductImageError", {
        currentTarget: { dataset: { id: productTarget.id } },
      });
      await sleep(300);
      failed = await readHomeImageFailed(page, "products", productTarget.blockIndex, productTarget.productIndex);
    }
    const fallbacks = await page.$$(".shelf .product-card .yunxi-image-fallback");
    const shelfAfter = shelf ? await shelf.size() : null;
    audit.details.push(
      `商品图降级：imageFailed=${failed}，占位从 ${fallbackBefore.length} 增至 ${fallbacks.length}，触发方式=${trigger}`
    );
    if (shelfBefore && shelfAfter) {
      audit.details.push(`货架高度：${shelfBefore.height}px -> ${shelfAfter.height}px`);
    }
    if (!failed || fallbacks.length <= fallbackBefore.length) {
      audit.errors.push("首页商品图加载失败后未切换到可视占位");
    }
    if (shelfBefore && shelfAfter && Math.abs(shelfBefore.height - shelfAfter.height) > 1) {
      audit.errors.push(`首页商品图降级后货架高度跳动：${shelfBefore.height}px -> ${shelfAfter.height}px`);
    }
    await page.setData({
      [`${productPath}.imageUrl`]: productTarget.imageUrl,
      [`${productPath}.imageFailed`]: false,
    });
  } else {
    audit.details.push("首页无可用商品图，跳过商品图降级验证");
  }

  if (heroTarget) {
    const heroPath = `blocks[${heroTarget.blockIndex}].heroItems[${heroTarget.slideIndex}]`;
    await page.setData({
      [`${heroPath}.imageUrl`]: brokenImageUrl,
      [`${heroPath}.imageFailed`]: false,
    });
    let failed = await waitForHomeImageFailure(page, "heroItems", heroTarget.blockIndex, heroTarget.slideIndex);
    let trigger = "真实 binderror 事件";
    if (!failed) {
      trigger = "直接调用失败回调（真实事件未在 6s 内触发）";
      await page.callMethod("onHeroImageError", {
        currentTarget: { dataset: { slideId: heroTarget.id } },
      });
      await sleep(300);
      failed = await readHomeImageFailed(page, "heroItems", heroTarget.blockIndex, heroTarget.slideIndex);
    }
    const heroFallback = await page.$(".home-hero__fallback");
    const heroFallbackSize = heroFallback ? await heroFallback.size() : null;
    audit.details.push(
      `轮播图降级：imageFailed=${failed}，占位高度=${heroFallbackSize ? heroFallbackSize.height : 0}px，触发方式=${trigger}`
    );
    if (!failed || !heroFallbackSize || heroFallbackSize.height <= 0) {
      audit.errors.push("首页轮播图加载失败后未切换到可视占位");
    }
    await page.setData({
      [`${heroPath}.imageUrl`]: heroTarget.imageUrl,
      [`${heroPath}.imageFailed`]: false,
    });
  } else {
    audit.details.push("首页轮播图无可用图片，跳过轮播降级验证");
  }

  if (audit.errors.length > 0) {
    audit.ok = false;
    result.errors.push(...audit.errors);
  }
}

// 表单字段标签验证：输入控件必须有常驻标签，且标签在控件上方不重叠。
async function inspectFormFieldLabels(page, pageDef, result) {
  const audit = { ok: true, details: [], errors: [] };
  result.formFieldLabels = audit;
  let fields = await page.$$(".form-field, .quantity-field");
  let enteredEditMode = false;
  let seededCheckoutItems = false;
  let previousCheckoutState = { isLoggedIn: false, checkoutItems: [] };
  if (fields.length === 0 && pageDef.path === "pages/checkout/index") {
    const previousData = await page.data();
    previousCheckoutState = {
      isLoggedIn: Boolean(previousData.isLoggedIn),
      checkoutItems: Array.isArray(previousData.checkoutItems) ? previousData.checkoutItems : []
    };
    await page.setData({
      isLoggedIn: true,
      checkoutItems: [
        {
          productId: "form-label-audit",
          title: "表单标签审计样本",
          imageUrl: "",
          priceFen: 1000,
          priceText: "¥10.00",
          quantity: 1,
        },
      ],
    });
    await sleep(300);
    fields = await page.$$(".form-field, .quantity-field");
    seededCheckoutItems = fields.length > 0;
  }
  if (fields.length === 0 && pageDef.path === "pages/address/index") {
    await page.callMethod("startCreate");
    await sleep(400);
    fields = await page.$$(".form-field, .quantity-field");
    enteredEditMode = fields.length > 0;
  }
  if (fields.length === 0) {
    audit.details.push("当前页面状态未渲染表单字段，跳过常驻标签断言");
    return;
  }
  let labeledControls = 0;
  for (let index = 0; index < fields.length; index++) {
    const field = fields[index];
    const label = (await field.$(".form-field__label")) || (await field.$(".quantity-field__label"));
    const controls = await field.$$("input, textarea");
    if (!label || controls.length === 0) {
      audit.errors.push(`第 ${index + 1} 个表单字段缺少常驻标签或输入控件`);
      continue;
    }
    labeledControls += controls.length;
    const labelText = (await label.text()).trim();
    const labelSize = await label.size();
    const labelOffset = await label.offset();
    const controlSize = await controls[0].size();
    const controlOffset = await controls[0].offset();
    const layout = controlOffset.left >= labelOffset.left + labelSize.width - 1 ? "行内" : "上方";
    audit.details.push(`${labelText || "无标签"}：${layout}标签，控件 ${controlSize.width}x${controlSize.height}px`);
    if (!labelText) {
      audit.errors.push(`第 ${index + 1} 个表单字段标签文案为空`);
    }
    const overlapX =
      Math.min(labelOffset.left + labelSize.width, controlOffset.left + controlSize.width) -
      Math.max(labelOffset.left, controlOffset.left);
    const overlapY =
      Math.min(labelOffset.top + labelSize.height, controlOffset.top + controlSize.height) -
      Math.max(labelOffset.top, controlOffset.top);
    if (overlapX > 1 && overlapY > 1) {
      audit.errors.push(`表单字段“${labelText}”标签与输入控件重叠`);
    }
    if (controlSize.height < 44) {
      audit.errors.push(`表单字段“${labelText}”输入控件高度不足 44px：${controlSize.height}px`);
    }
  }
  const allControls = await page.$$("input, textarea");
  if (allControls.length > labeledControls) {
    audit.errors.push(`存在 ${allControls.length - labeledControls} 个未使用常驻标签的输入控件`);
  }
  if (enteredEditMode) {
    await page.callMethod("cancelEdit");
    await sleep(200);
  }
  if (seededCheckoutItems) {
    // 播种态的登录标志也必须还原，否则后续按钮扫描和未登录断言会读到泄漏状态。
    await page.setData(previousCheckoutState);
    await sleep(200);
  }
  if (audit.errors.length > 0) {
    audit.ok = false;
    result.errors.push(...audit.errors);
  }
}

// 商品详情悬浮栏在滚动后必须切实底：透明悬浮栏会让正文穿透到状态栏与返回控件下方。
async function inspectProductDetailScrollNav(page, pageDef, result) {
  if (pageDef.path !== "pages/product-detail/index") {
    return;
  }
  const detailPageData = await page.data();
  if (!detailPageData || !detailPageData.product) {
    result.detailScrollNav = { ok: true, skipped: true, reason: "当前为商品详情空态，悬浮栏滚动断言由真实商品流程覆盖" };
    return;
  }
  const audit = {
    ok: false,
    initialClass: "",
    scrolledClass: "",
    scrolledBackground: "",
    restoredClass: "",
    restoredBackground: "",
    errors: []
  };
  const nav = await page.$(".detail-nav");
  const scrollView = await page.$(".page-scroll");
  if (!nav || !scrollView) {
    audit.errors.push("商品详情缺少悬浮栏或滚动容器");
  } else {
    const initialClass = (await nav.attribute("class")) || "";
    audit.initialClass = initialClass;
    if (initialClass.includes("detail-nav--solid")) {
      audit.errors.push("商品详情首屏悬浮栏不应为实底，应与商品大图融为一体");
    }
    let scrollHeight = 0;
    try {
      scrollHeight = await scrollView.scrollHeight();
    } catch (error) {
      scrollHeight = 0;
    }
    if (!scrollHeight || scrollHeight < 200) {
      audit.errors.push(`商品详情滚动高度不足，无法验证悬浮栏：${scrollHeight}`);
    } else {
      await scrollView.scrollTo(0, 240);
      const scrolledState = await waitForDetailNavState(nav, true);
      audit.scrolledClass = scrolledState.className;
      audit.scrolledBackground = await waitForDetailNavBackground(nav, true);
      const scrolledColor = parseCssColor(audit.scrolledBackground);
      if (!audit.scrolledClass.includes("detail-nav--solid")) {
        audit.errors.push("商品详情滚动后悬浮栏未切换实底状态");
      }
      if (!scrolledColor || scrolledColor.a < 0.9) {
        audit.errors.push(`商品详情滚动后悬浮栏背景仍不透明可穿透：${audit.scrolledBackground}`);
      }
      await scrollView.scrollTo(0, 0);
      const restoredState = await waitForDetailNavState(nav, false);
      audit.restoredClass = restoredState.className;
      audit.restoredBackground = await waitForDetailNavBackground(nav, false);
      if (audit.restoredClass.includes("detail-nav--solid")) {
        audit.errors.push("商品详情回到顶部后悬浮栏未恢复透明");
      }
      const restoredColor = parseCssColor(audit.restoredBackground);
      if (restoredColor && restoredColor.a > 0.5) {
        audit.errors.push(`商品详情回到顶部后悬浮栏仍为实底：${audit.restoredBackground}`);
      }
    }
  }
  audit.ok = audit.errors.length === 0;
  result.detailScrollNav = audit;
  result.errors.push(...audit.errors);
}

// 商品目录导航头验证：自定义 TabBar 已提供首页入口，页头不得再出现不可见主页控件，门店名也不得在页头与固定信息卡重复。
async function inspectProductsHeader(page, pageDef, result) {
  if (pageDef.path !== "pages/products/index") {
    return;
  }
  const audit = { ok: true, details: [], errors: [] };
  result.productsHeader = audit;
  const hiddenHomeControls = await page.$$(".page-fixed-safe__home");
  audit.hiddenHomeControlCount = hiddenHomeControls.length;
  if (hiddenHomeControls.length > 0) {
    audit.errors.push(`商品目录页头仍存在 ${hiddenHomeControls.length} 个不可见主页控件`);
  }
  const navTitle = await page.$(".page-fixed-safe__title");
  const navTitleText = navTitle ? (await navTitle.text()).trim() : "";
  const branchLabel = await page.$(".products-pinned .products-store__branch");
  const branchText = branchLabel ? (await branchLabel.text()).trim() : "";
  audit.navTitleText = navTitleText;
  audit.branchText = branchText;
  audit.details.push(`页头标题="${navTitleText}"，固定信息卡门店="${branchText}"`);
  if (!branchText) {
    audit.errors.push("商品目录固定信息卡缺少门店名称");
  }
  if (navTitleText && branchText && navTitleText.includes(branchText)) {
    audit.errors.push(`商品目录页头标题与固定信息卡门店名重复："${navTitleText}" 包含 "${branchText}"`);
  }
  const fixedSafe = await page.$(".page-fixed-safe");
  if (fixedSafe) {
    const fixedSafeSize = await fixedSafe.size();
    audit.fixedSafeHeight = fixedSafeSize.height;
    audit.details.push(`页头容器高度=${fixedSafeSize.height}px`);
    if (!fixedSafeSize.height || fixedSafeSize.height < 20) {
      audit.errors.push(`商品目录页头容器高度异常：${fixedSafeSize.height}px`);
    }
  } else {
    audit.errors.push("商品目录缺少 .page-fixed-safe 页头容器");
  }
  audit.ok = audit.errors.length === 0;
  if (audit.errors.length > 0) {
    result.errors.push(...audit.errors);
  }
}

async function inspectCommerceState(page, pageDef, result) {
  const commerce = { ok: true, details: [], errors: [] };
  const data = await page.data();

  if (pageDef.path === "pages/home/index") {
    const apiShelfCount = await fetchHomeShelfLimitCount(6);
    let shelf = await page.$(".shelf");
    let cards = await page.$$(".shelf .product-card");
    for (
      let attempt = 0;
      attempt < 8 && (!shelf || cards.length === 0 || (apiShelfCount !== null && cards.length < apiShelfCount));
      attempt++
    ) {
      await sleep(400);
      shelf = await page.$(".shelf");
      cards = await page.$$(".shelf .product-card");
    }
    const hero = await page.$(".home-hero");
    if (!shelf || cards.length === 0) {
      commerce.errors.push("商品优先：首页首屏未找到包含商品的货架");
    } else {
      const shelfOffset = await shelf.offset();
      const firstCardOffset = await cards[0].offset();
      commerce.details.push(`货架顶部=${shelfOffset.top}px，首张商品=${firstCardOffset.top}px，商品数=${cards.length}`);
      if (apiShelfCount === null) {
        commerce.details.push("货架条数交叉校验：接口不可用，已跳过");
      } else {
        commerce.details.push(`货架条数交叉校验：接口=${apiShelfCount}，渲染=${cards.length}`);
        if (cards.length !== apiShelfCount) {
          commerce.errors.push(
            `首页货架商品数与精选接口不一致：渲染=${cards.length}，接口=${apiShelfCount}`
          );
        }
      }
      if (shelfOffset.top > 220 || firstCardOffset.top > 260) {
        commerce.errors.push("商品优先：首页首屏商品位置过低");
      }
      if (hero) {
        const heroOffset = await hero.offset();
        commerce.details.push(`品牌轮播顶部=${heroOffset.top}px`);
        if (heroOffset.top <= shelfOffset.top) {
          commerce.errors.push("商品优先：首页品牌轮播未排在商品货架之后");
        }
      }
      const shelfEyebrow = await page.$(".shelf-head__eyebrow");
      const shelfTitle = await page.$(".shelf-head__title");
      const shelfSubtitle = await page.$(".shelf-head__subtitle");
      const shelfLink = await page.$(".shelf-head__link");
      if (!shelfEyebrow || !shelfTitle) {
        commerce.errors.push("商品货架缺少标题层级（eyebrow/title）");
      } else {
        const eyebrowOffset = await shelfEyebrow.offset();
        const eyebrowSize = await shelfEyebrow.size();
        const titleOffset = await shelfTitle.offset();
        const titleSize = await shelfTitle.size();
        const subtitleOffset = shelfSubtitle ? await shelfSubtitle.offset() : null;
        const linkOffset = shelfLink ? await shelfLink.offset() : null;
        const linkSize = shelfLink ? await shelfLink.size() : null;
        commerce.details.push(
          `货架标题层级：鲜制=${eyebrowOffset.top}px，标题=${titleOffset.top}px${subtitleOffset ? `，副标题=${subtitleOffset.top}px` : ""}`
        );
        if (eyebrowOffset.top + eyebrowSize.height > titleOffset.top + 1) {
          commerce.errors.push("货架标题层级未垂直排列：eyebrow 与标题重叠");
        }
        if (subtitleOffset && titleOffset.top + titleSize.height > subtitleOffset.top + 1) {
          commerce.errors.push("货架标题层级未垂直排列：标题与副标题重叠");
        }
        if (linkOffset && linkSize) {
          const overlapX =
            Math.min(titleOffset.left + titleSize.width, linkOffset.left + linkSize.width) -
            Math.max(titleOffset.left, linkOffset.left);
          const overlapY =
            Math.min(titleOffset.top + titleSize.height, linkOffset.top + linkSize.height) -
            Math.max(titleOffset.top, linkOffset.top);
          if (overlapX > 1 && overlapY > 1) {
            commerce.errors.push("商品货架标题与“查看更多”入口相互重叠");
          }
        }

        // 服务承诺卡承载截单时间与配送规则，必须完整可读，不得单行截断或字号过小。
        const promiseItems = await page.$$(".shop-promise-item");
        const promiseDescs = await page.$$(".shop-promise-desc");
        if (promiseItems.length !== 3 || promiseDescs.length !== 3) {
          commerce.errors.push(`首页服务承诺卡应为 3 项：卡片=${promiseItems.length}，说明=${promiseDescs.length}`);
        } else {
          const promiseTexts = [];
          let minPromiseFontSize = Number.POSITIVE_INFINITY;
          for (const desc of promiseDescs) {
            promiseTexts.push((await desc.text()).trim());
            const fontSize = Number.parseFloat(await desc.style("font-size"));
            if (Number.isFinite(fontSize)) {
              minPromiseFontSize = Math.min(minPromiseFontSize, fontSize);
            }
          }
          commerce.details.push(`服务承诺说明：${promiseTexts.join(" / ")}；最小字号=${minPromiseFontSize}px`);
          if (!promiseTexts[2].includes("17:00 截单")) {
            commerce.errors.push(`首页服务承诺未声明真实截单时间：${promiseTexts[2]}`);
          }
          if (minPromiseFontSize < 10) {
            commerce.errors.push(`首页服务承诺说明字号过小：${minPromiseFontSize}px`);
          }
        }

        const promiseIcons = await page.$$(".shop-promise-icon");
        if (promiseIcons.length !== 3) {
          commerce.errors.push(`首页服务承诺图标应为 3 个：当前=${promiseIcons.length}`);
        } else {
          const iconDetails = [];
          for (const icon of promiseIcons) {
            const iconText = (await icon.text()).trim();
            const backgroundImage = (await icon.style("background-image")) || "";
            const size = await icon.size();
            const ariaHidden = await icon.attribute("aria-hidden");
            iconDetails.push(`${Math.round(size.width)}x${Math.round(size.height)}`);
            if (iconText) {
              commerce.errors.push(`首页服务承诺图标不得使用文字：${iconText}`);
            }
            if (!backgroundImage || backgroundImage === "none") {
              commerce.errors.push("首页服务承诺图标缺少可渲染背景图");
            }
            if (size.width < 12 || size.height < 12) {
              commerce.errors.push(`首页服务承诺图标尺寸不足：${Math.round(size.width)}x${Math.round(size.height)}px`);
            }
            if (ariaHidden !== "true") {
              commerce.errors.push("首页服务承诺图标必须标记 aria-hidden");
            }
          }
          commerce.details.push(`服务承诺图标：${iconDetails.join(" / ")}`);
        }

        const quickLinkIcons = await page.$$(".quick-link-card__icon");
        for (const icon of quickLinkIcons) {
          const iconText = (await icon.text()).trim();
          const backgroundImage = (await icon.style("background-image")) || "";
          const size = await icon.size();
          const ariaHidden = await icon.attribute("aria-hidden");
          if (iconText) {
            commerce.errors.push(`首页快捷入口图标不得使用文字：${iconText}`);
          }
          if (!backgroundImage || backgroundImage === "none") {
            commerce.errors.push("首页快捷入口图标缺少可渲染背景图");
          }
          if (size.width < 12 || size.height < 12) {
            commerce.errors.push(`首页快捷入口图标尺寸不足：${Math.round(size.width)}x${Math.round(size.height)}px`);
          }
          if (ariaHidden !== "true") {
            commerce.errors.push("首页快捷入口图标必须标记 aria-hidden");
          }
        }
        if (quickLinkIcons.length > 0) {
          commerce.details.push(`首页快捷入口图标数量=${quickLinkIcons.length}`);
        }

        // 商品卡购买说明必须完整可读：字号不低于 11px，且不得溢出所在卡片。
        const productTips = await page.$$(".shelf .product-card .product-tip");
        if (productTips.length === 0) {
          commerce.errors.push("首页商品卡缺少购买说明");
        } else {
          const cardBoxes = [];
          for (const card of cards) {
            cardBoxes.push({ offset: await card.offset(), size: await card.size() });
          }
          let minTipFontSize = Number.POSITIVE_INFINITY;
          let maxTipOverflow = 0;
          let maxTipLines = 0;
          for (const tip of productTips) {
            const fontSize = Number.parseFloat(await tip.style("font-size"));
            const lineHeight = Number.parseFloat(await tip.style("line-height"));
            if (Number.isFinite(fontSize)) {
              minTipFontSize = Math.min(minTipFontSize, fontSize);
            }
            const tipOffset = await tip.offset();
            const tipSize = await tip.size();
            const owningCard = cardBoxes.find(
              (box) =>
                tipOffset.left >= box.offset.left - 1 &&
                tipOffset.left < box.offset.left + box.size.width
            );
            if (owningCard) {
              const cardRight = owningCard.offset.left + owningCard.size.width;
              maxTipOverflow = Math.max(maxTipOverflow, tipOffset.left + tipSize.width - cardRight);
            }
            const effectiveLineHeight = Number.isFinite(lineHeight) && lineHeight > 0 ? lineHeight : fontSize * 1.35;
            if (Number.isFinite(effectiveLineHeight) && effectiveLineHeight > 0) {
              maxTipLines = Math.max(maxTipLines, Math.round(tipSize.height / effectiveLineHeight));
            }
          }
          commerce.details.push(
            `商品卡购买说明：条数=${productTips.length}，最小字号=${minTipFontSize}px，最大溢出=${maxTipOverflow.toFixed(1)}px，最大行数≈${maxTipLines}`
          );
          if (minTipFontSize < 11) {
            commerce.errors.push(`首页商品卡购买说明字号过小：${minTipFontSize}px`);
          }
          if (maxTipOverflow > 1) {
            commerce.errors.push(`首页商品卡购买说明溢出卡片：${maxTipOverflow.toFixed(1)}px`);
          }
          if (maxTipLines > 3) {
            commerce.errors.push(`首页商品卡购买说明行数过多：${maxTipLines} 行`);
          }
        }
      }
    }
  }

  if (pageDef.path === "pages/products/index") {
    const legacyToggle = await page.$(".products-toggle");
    const serviceNote = await page.$(".products-service-note");
    const cards = await page.$$(".products-content .product-card");
    commerce.details.push(`商品卡=${cards.length}，商品分区=${Array.isArray(data.categorySections) ? data.categorySections.length : 0}`);
    if (legacyToggle) {
      commerce.errors.push("商品页仍展示不具备筛选能力的配送切换");
    }
    if (!serviceNote) {
      commerce.errors.push("商品页缺少自提价与北京闪送运费说明");
    }
  }

  if (pageDef.path === "pages/cart/index" && data.hasItems === false) {
    const footer = await page.$(".cart-footer");
    commerce.details.push("当前为空购物车");
    if (footer) {
      commerce.errors.push("空购物车仍展示金额结算栏");
    }
  }

  if (pageDef.path === "pages/checkout/index" && data.isLoggedIn === false) {
    const form = await page.$(".form");
    const footer = await page.$(".checkout-footer");
    commerce.details.push("当前为未登录结算态");
    if (form || footer) {
      commerce.errors.push("未登录结算态仍展示交易表单或提交动作");
    }
  }

  if (pageDef.path === "pages/product-detail/index" && data.canPurchase === false) {
    const actions = await page.$(".detail-actions");
    commerce.details.push("当前为不可购买商品态");
    if (actions) {
      commerce.errors.push("不可购买商品仍展示购买操作");
    }
  }

  commerce.ok = commerce.errors.length === 0;
  result.commerce = commerce;
  result.errors.push(...commerce.errors);
}

// 未登录引导空态在各页面保持同一套信息结构：图标、标题、说明、去登录按钮；
// 按钮需满足 44px 触控基线，且不得同时渲染受限业务内容。
async function inspectLoginGate(page, pageDef, result) {
  if (!LOGIN_GATE_PAGES.includes(pageDef.path)) {
    return;
  }
  const previous = await page.data();
  const previousSessionView = previous.sessionView || {};
  const seeds = {
    "pages/orders/index": {
      sessionView: { ...previousSessionView, loggedIn: false, badgeText: "未登录" },
      loginStateText: "登录后可查看制作、自提与配送进度"
    },
    "pages/address/index": {
      sessionView: { ...previousSessionView, loggedIn: false, badgeText: "未登录" },
      loginStateText: "登录后可保存常用地址，下单直接选择"
    },
    "pages/order-detail/index": {
      sessionView: { ...previousSessionView, loggedIn: false, badgeText: "未登录" },
      loginStateText: "登录后可查看金额明细与履约进度",
      canLoadOrder: false,
      order: null,
      loading: false
    },
    "pages/coupons/index": { loggedIn: false, loading: false },
    "pages/points/index": { loggedIn: false, loading: false },
    "pages/recharge/index": { loggedIn: false, ready: false },
    "pages/checkout/index": { isLoggedIn: false }
  };
  const seed = seeds[pageDef.path];
  await page.setData(seed);
  await sleep(260);
  try {
    const gate = await page.$(".yunxi-state");
    const icon = gate ? await gate.$(".yunxi-state__icon") : null;
    const title = gate ? await gate.$(".yunxi-state__title") : null;
    const hint = gate ? await gate.$(".yunxi-state__hint") : null;
    const action = gate ? await gate.$(".yunxi-state__action") : null;
    if (!gate || !icon || !title || !hint || !action) {
      result.errors.push(pageDef.path + ": 未登录时缺少图标+标题+说明+去登录按钮的登录引导空态");
      return;
    }
    const iconText = (await icon.text()).trim();
    const iconSize = await icon.size();
    const iconBackground = (await icon.style("background-image")) || "";
    const titleText = (await title.text()).trim();
    const hintText = (await hint.text()).trim();
    const actionText = (await action.text()).trim();
    const actionSize = await action.size();
    const hintSize = await hint.size();
    const hintLineHeight = Number.parseFloat(await hint.style("line-height"));
    const gateSize = await gate.size();
    result.loginGate = {
      iconText,
      iconBackground: iconBackground === "none" ? "" : "set",
      iconSize: `${Math.round(iconSize.width)}x${Math.round(iconSize.height)}`,
      titleText,
      hintText,
      hintSize: `${Math.round(hintSize.width)}x${Math.round(hintSize.height)}`,
      actionText,
      actionSize: `${Math.round(actionSize.width)}x${Math.round(actionSize.height)}`,
      gateSize: `${Math.round(gateSize.width)}x${Math.round(gateSize.height)}`
    };
    if (gateSize.height < 260) {
      result.errors.push(
        pageDef.path + `: 登录引导空态未占据整页高度（${Math.round(gateSize.height)}px）`
      );
    }
    if (Number.isFinite(hintLineHeight) && hintSize.height > hintLineHeight * 1.45) {
      result.errors.push(
        pageDef.path + `: 登录引导说明文案换行（${Math.round(hintSize.height)}px / 行高 ${hintLineHeight}px）`
      );
    }
    if (iconText) {
      result.errors.push(pageDef.path + `: 登录引导空态不得用文字充当图标（${iconText}）`);
    }
    if (!iconBackground || iconBackground === "none") {
      result.errors.push(pageDef.path + ": 登录引导空态图标缺少可渲染背景图");
    }
    if (iconSize.width < 32 || iconSize.height < 32) {
      result.errors.push(
        pageDef.path + `: 登录引导空态图标渲染尺寸不足（${Math.round(iconSize.width)}x${Math.round(iconSize.height)}px）`
      );
    }
    if (titleText.length < 4) {
      result.errors.push(pageDef.path + `: 登录引导空态标题过短（${titleText || "空"}）`);
    }
    if (hintText.length < 6) {
      result.errors.push(pageDef.path + `: 登录引导空态说明过短（${hintText || "空"}）`);
    }
    if (!hintText.includes("登录")) {
      result.errors.push(pageDef.path + `: 登录引导空态说明未点明登录价值（${hintText || "空"}）`);
    }
    if (actionText !== "去登录") {
      result.errors.push(pageDef.path + `: 登录引导空态按钮文案应为去登录（当前 ${actionText || "空"}）`);
    }
    if (actionSize.width < 48 || actionSize.height < 44) {
      result.errors.push(
        pageDef.path + `: 登录引导按钮触控尺寸不足（${Math.round(actionSize.width)}x${Math.round(actionSize.height)}px）`
      );
    }
    for (const selector of LOGIN_GATE_LIMITED_CONTENT[pageDef.path] || []) {
      if (await page.$(selector)) {
        result.errors.push(pageDef.path + `: 未登录时仍展示受限业务内容（${selector}）`);
        break;
      }
    }
  } finally {
    const restore = {};
    for (const key of Object.keys(seed)) {
      restore[key] = previous[key];
    }
    await page.setData(restore);
    await sleep(160);
  }
}

async function inspectSessionAndAuthState(page, pageDef, result, viewportWidth) {
  const data = await page.data();
  const sessionView = data.sessionView || {};
  const notice = await page.$(".session-notice");
  const action = await page.$(".session-notice__button");
  const noticeIcon = await page.$(".session-notice__icon");

  // 会话提示需占满内容宽度：居中空态曾将宿主节点压成内容宽度，造成标题换行与副文案截断。
  if (notice && viewportWidth) {
    const noticeWidth = (await notice.size()).width;
    result.sessionNoticeWidth = `${Math.round(noticeWidth)}/${viewportWidth}`;
    if (noticeWidth < viewportWidth * 0.85) {
      result.errors.push(
        pageDef.path + `: 会话提示卡片横向收窄（${Math.round(noticeWidth)}px / ${viewportWidth}px）`
      );
    }
  }

  // 身份徽标必须渲染为线性图标：单个汉字（如“我/登”）在截图上与未替换的占位稿无法区分。
  if (noticeIcon) {
    const badgeText = (await noticeIcon.text()).trim();
    const badgeSize = await noticeIcon.size();
    const badgeBackground = (await noticeIcon.style("background-image")) || "";
    result.sessionNoticeBadge = {
      text: badgeText,
      size: `${Math.round(badgeSize.width)}x${Math.round(badgeSize.height)}`,
      background: badgeBackground === "none" ? "" : "set"
    };
    if (badgeText) {
      result.errors.push(pageDef.path + `: 会话提示徽标不得用文字充当图标（${badgeText}）`);
    }
    if (!badgeBackground || badgeBackground === "none") {
      result.errors.push(pageDef.path + ": 会话提示徽标缺少可渲染背景图");
    }
    if (badgeSize.width < 16 || badgeSize.height < 16) {
      result.errors.push(
        pageDef.path + `: 会话提示徽标渲染尺寸不足（${Math.round(badgeSize.width)}x${Math.round(badgeSize.height)}px）`
      );
    }
  }

  if (notice) {
    if (!action && sessionView.loggedIn === false) {
      result.errors.push(pageDef.path + ": 未登录会话提示缺少登录操作");
    }
    if (action) {
      const text = (await action.text()).trim();
      const size = await action.size();
      const ariaLabel = (await action.attribute("aria-label")) || "";
      result.sessionNotice = {
        actionText: text,
        actionAriaLabel: ariaLabel,
        actionSize: size.width + "x" + size.height
      };
      if (!text) {
        result.errors.push(pageDef.path + ": 会话提示操作按钮为空白");
      }
      if (size.width < 48 || size.height < 44) {
        result.errors.push(pageDef.path + ": 会话提示操作按钮尺寸过小");
      }
      if (ariaLabel && ariaLabel !== text) {
        result.errors.push(pageDef.path + ": 会话提示 aria-label 与按钮文本不一致");
      }
    }
  }

  await inspectLoginGate(page, pageDef, result);
}

// 顾客可见区域不得泄露登录态实现、演示模式、虚假会员等级或占位头像。
// 个人中心的订单与服务入口图标必须是可渲染的线性图标；只检查元素存在会放过空白占位方块。
async function inspectProfileShortcuts(page, pageDef, result) {
  const orderIcons = await page.$$(".order-nav-icon");
  const serviceIcons = await page.$$(".service-cell__icon");
  result.profileShortcutIcons = { order: orderIcons.length, service: serviceIcons.length };

  if (orderIcons.length < 4) {
    result.errors.push(pageDef.path + `: 订单入口数量异常（${orderIcons.length}）`);
  }
  if (serviceIcons.length < 5) {
    result.errors.push(pageDef.path + `: 服务入口数量异常（${serviceIcons.length}）`);
  }
  const iconSamples = [];
  for (const [selector, icons, label] of [
    [".order-nav-icon", orderIcons, "订单入口图标"],
    [".service-cell__icon", serviceIcons, "服务入口图标"],
  ]) {
    if (!icons.length) {
      continue;
    }
    let reported = false;
    for (const icon of icons) {
      const text = (await icon.text()).trim();
      const size = await icon.size();
      const backgroundImage = (await icon.style("background-image")) || "";
      iconSamples.push(`${selector}:${Math.round(size.width)}x${Math.round(size.height)}`);
      if (!backgroundImage || backgroundImage === "none") {
        result.errors.push(pageDef.path + `: ${label}缺少可渲染背景图标（${selector}）`);
        reported = true;
        break;
      }
      if (text) {
        result.errors.push(pageDef.path + `: ${label}不得再用文字占位（${text}）`);
        reported = true;
        break;
      }
      if (size.width < 16 || size.height < 16) {
        result.errors.push(
          pageDef.path + `: ${label}渲染尺寸不足（${Math.round(size.width)}x${Math.round(size.height)}px）`
        );
        reported = true;
        break;
      }
    }
    if (reported) {
      continue;
    }
  }
  result.profileShortcutIconSamples = iconSamples;

  // 头像要么是可辨认的图形，要么是有姓名的首字；未登录/无姓名时不得用单字占位。
  const avatar = await page.$(".profile-avatar");
  const pageData = await page.data();
  const loggedIn = Boolean(pageData.sessionView?.loggedIn);
  const memberName = String(pageData.memberProps?.name || "").trim();
  const avatarText = avatar ? (await avatar.text()).trim() : "";
  const avatarBackground = avatar ? ((await avatar.style("background-image")) || "") : "";
  result.profileAvatar = {
    loggedIn,
    hasMemberName: Boolean(memberName),
    textLength: avatarText.length,
    hasIconBackground: Boolean(avatarBackground && avatarBackground !== "none"),
  };
  if (!avatar) {
    result.errors.push(pageDef.path + ": 缺少会员头像容器");
  } else if (!loggedIn || !memberName) {
    if (avatarText) {
      result.errors.push(pageDef.path + `: 未登录或无姓名头像不得渲染单字占位（${avatarText}）`);
    }
    if (!avatarBackground || avatarBackground === "none") {
      result.errors.push(pageDef.path + ": 未登录或无姓名头像缺少可渲染的人像图标");
    }
  } else if (avatarText !== memberName[0]) {
    result.errors.push(pageDef.path + ": 已登录头像首字与会员姓名不一致");
  }
}

async function inspectCustomerFacingCopy(page, pageDef, result) {
  const pageRoot = await page.$(".page");
  if (!pageRoot) {
    return;
  }
  const text = (await pageRoot.text()).trim();
  const banned = ["真实登录态", "演示会话", "VIP 会员", "8888 6666", "👤"];
  const matched = banned.filter((item) => text.includes(item));
  result.customerCopy = {
    ok: matched.length === 0,
    matched,
    textLength: text.length
  };
  for (const item of matched) {
    result.errors.push(`${pageDef.path}: 顾客可见区域仍包含工程或占位文案“${item}”`);
  }
}

function parseCssColor(value) {
  const text = String(value || "").trim().toLowerCase();
  if (text === "transparent") {
    return { r: 0, g: 0, b: 0, a: 0 };
  }
  const match = text.match(/^rgba?\(\s*([\d.]+)\s*[, ]\s*([\d.]+)\s*[, ]\s*([\d.]+)(?:\s*[,/]\s*([\d.]+))?\s*\)$/);
  if (!match) {
    return null;
  }
  return {
    r: Number(match[1]),
    g: Number(match[2]),
    b: Number(match[3]),
    a: match[4] === undefined ? 1 : Number(match[4]),
  };
}

function blendCssColor(foreground, background) {
  const alpha = Math.max(0, Math.min(1, foreground.a));
  return {
    r: foreground.r * alpha + background.r * (1 - alpha),
    g: foreground.g * alpha + background.g * (1 - alpha),
    b: foreground.b * alpha + background.b * (1 - alpha),
    a: 1,
  };
}

function relativeLuminance(color) {
  const channel = (value) => {
    const normalized = value / 255;
    return normalized <= 0.03928
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(color.r) + 0.7152 * channel(color.g) + 0.0722 * channel(color.b);
}

function contrastRatio(foreground, background) {
  const resolvedForeground = blendCssColor(foreground, background);
  const lighter = Math.max(relativeLuminance(resolvedForeground), relativeLuminance(background));
  const darker = Math.min(relativeLuminance(resolvedForeground), relativeLuminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}

async function inspectDisabledButtonStyle(button, label, audit) {
  const color = parseCssColor(await button.style("color"));
  const background = parseCssColor(await button.style("background-color"));
  const size = await button.size();
  if (!color || !background || background.a === 0) {
    audit.errors.push(`${label}禁用态缺少可解析的前景或背景色`);
    return;
  }
  const ratio = contrastRatio(color, background);
  audit.details.push(
    `${label}禁用态：${size.width}x${size.height}px，对比度 ${ratio.toFixed(2)}:1`
  );
  if (ratio < 4.5) {
    audit.errors.push(`${label}禁用态文字对比度不足 4.5:1：${ratio.toFixed(2)}:1`);
  }
}

async function inspectInteractionStates(page, pageDef, result) {
  const audit = { ok: true, details: [], errors: [] };
  result.interactionStates = audit;

  if (pageDef.path === "pages/recharge/index") {
    const data = await page.data();
    const previousRechargeState = {
      loggedIn: Boolean(data.loggedIn),
      ready: Boolean(data.ready),
      submitting: Boolean(data.submitting),
    };
    const seededRechargeState = !data.loggedIn || !data.ready;
    if (seededRechargeState) {
      await page.setData({ loggedIn: true, ready: true });
      await sleep(300);
    }
    const label = await page.$(".custom-label");
    const inputWrap = await page.$(".custom-input-wrap");
    const input = await page.$(".custom-input");
    const unit = await page.$(".custom-unit");
    if (!label || !inputWrap || !input || !unit) {
      if (seededRechargeState || (data.loggedIn && data.ready)) {
        audit.errors.push("充值页缺少自定义金额标签、输入框或单位");
      }
    } else {
      const labelText = (await label.text()).trim();
      const wrapSize = await inputWrap.size();
      const inputSize = await input.size();
      const wrapOffset = await inputWrap.offset();
      const inputOffset = await input.offset();
      const unitOffset = await unit.offset();
      const unitSize = await unit.size();
      const wrapBackground = parseCssColor(await inputWrap.style("background-color"));
      const borderTopWidth = Number.parseFloat(await inputWrap.style("border-top-width"));
      audit.details.push(
        `自定义金额：容器 ${wrapSize.width}x${wrapSize.height}px，输入框 ${inputSize.width}x${inputSize.height}px，单位=${labelText || "空"}`
      );
      if (labelText !== "自定义金额") {
        audit.errors.push(`充值页自定义金额标签文案异常：${labelText || "空"}`);
      }
      if (wrapSize.height < 44 || inputSize.height < 44) {
        audit.errors.push(`充值页自定义金额控件高度不足 44px：容器 ${wrapSize.height}px，输入框 ${inputSize.height}px`);
      }
      if (!wrapBackground || wrapBackground.a === 0 || !Number.isFinite(borderTopWidth) || borderTopWidth < 0.5) {
        audit.errors.push("充值页自定义金额输入框缺少可见背景或边框");
      }
      const overlapX =
        Math.min(inputOffset.left + inputSize.width, unitOffset.left + unitSize.width) -
        Math.max(inputOffset.left, unitOffset.left);
      const overlapY =
        Math.min(inputOffset.top + inputSize.height, unitOffset.top + unitSize.height) -
        Math.max(inputOffset.top, unitOffset.top);
      if (overlapX > 1 && overlapY > 1) {
        audit.errors.push("充值页自定义金额输入框与“元”单位重叠");
      }
      if (
        unitOffset.left < wrapOffset.left ||
        unitOffset.left + unitSize.width > wrapOffset.left + wrapSize.width + 1
      ) {
        audit.errors.push("充值页自定义金额单位超出输入框容器");
      }
    }

    const submit = await page.$(".recharge-page button.primary-btn");
    if (submit) {
      const previousSubmitting = Boolean(data.submitting);
      await page.setData({ submitting: true });
      await sleep(180);
      await inspectDisabledButtonStyle(submit, "充值提交按钮", audit);
      await page.setData({ submitting: previousSubmitting });
    }
    const hasRechargeRecords = Array.isArray(data.records) && data.records.length > 0;
    const recordsEmpty = hasRechargeRecords ? null : await page.$(".records-panel .records-empty");
    if (hasRechargeRecords) {
      audit.details.push(`充值记录：已有 ${data.records.length} 条，跳过空态断言`);
    } else if (recordsEmpty) {
      const title = await recordsEmpty.$(".yunxi-state__title");
      const hint = await recordsEmpty.$(".yunxi-state__hint");
      const emptySize = await recordsEmpty.size();
      const titleText = title ? (await title.text()).trim() : "";
      const hintText = hint ? (await hint.text()).trim() : "";
      audit.details.push(
        `充值记录空态：${titleText || "空"}；${hintText || "空"}；区域 ${emptySize.width}x${emptySize.height}px`
      );
      if (titleText !== "暂无充值记录" || !hintText.includes("充值成功后")) {
        audit.errors.push(`充值记录空态文案不完整：${titleText || "空"}/${hintText || "空"}`);
      }
      if (emptySize.height < 80) {
        audit.errors.push(`充值记录空态区域过小：${emptySize.height}px`);
      }
    } else {
      audit.errors.push("充值记录为空时缺少统一空态结构");
    }
    if (seededRechargeState) {
      await page.setData(previousRechargeState);
    }
  }

  if (pageDef.path === "pages/checkout/index") {
    const data = await page.data();
    const previousCanSubmit = Boolean(data.canSubmitOrder);
    const previousLoggedIn = Boolean(data.isLoggedIn);
    const previousItems = Array.isArray(data.checkoutItems) ? data.checkoutItems : [];
    let submit = await page.$(".checkout-footer__submit");
    let seededCheckoutItems = false;
    if (!submit) {
      await page.setData({
        isLoggedIn: true,
        checkoutItems: [
          {
            productId: "interaction-audit",
            title: "控件审计样本",
            imageUrl: "",
            priceFen: 1000,
            priceText: "¥10.00",
            quantity: 1,
          },
        ],
      });
      await sleep(300);
      submit = await page.$(".checkout-footer__submit");
      seededCheckoutItems = Boolean(submit);
    }
    if (submit) {
      if ((await submit.attribute("disabled")) === null) {
        await page.setData({ canSubmitOrder: false });
        await sleep(180);
      }
      await inspectDisabledButtonStyle(submit, "结算提交按钮", audit);
      await page.setData({ canSubmitOrder: previousCanSubmit });
    }

    // 无可用券时优惠券行只作信息展示，不应保留下拉箭头或展开空面板。
    const previousCoupons = Array.isArray(data.availableCoupons) ? data.availableCoupons : [];
    const previousCouponPanel = Boolean(data.showCouponPanel);
    const couponSampleItems = Array.isArray(data.checkoutItems) && data.checkoutItems.length
      ? data.checkoutItems
      : [
          {
            productId: "coupon-audit",
            title: "优惠券审计样本",
            imageUrl: "",
            priceFen: 1000,
            priceText: "¥10.00",
            quantity: 1,
          },
        ];
    await page.setData({
      isLoggedIn: true,
      checkoutItems: couponSampleItems,
      availableCoupons: [],
      showCouponPanel: false
    });
    await sleep(260);
    const couponRow = await page.$(".coupon-row");
    if (!couponRow) {
      audit.errors.push("结算页缺少优惠券行");
    } else {
      const couponValue = await couponRow.$(".benefit-value");
      const couponValueText = couponValue ? (await couponValue.text()).trim() : "";
      const couponArrow = await couponRow.$(".benefit-arrow");
      if (couponArrow) {
        audit.errors.push("无可用优惠券时优惠券行仍显示下拉箭头");
      }
      if (!couponValueText.includes("暂无可用")) {
        audit.errors.push(`无可用优惠券时缺少明确说明（${couponValueText || "空"}）`);
      }
      await couponRow.tap();
      await sleep(220);
      const couponPanel = await page.$(".coupon-panel");
      if (couponPanel) {
        audit.errors.push("无可用优惠券时点击仍展开空面板");
      }
      audit.details.push(
        `优惠券行：${couponValueText}；无下拉箭头=${!couponArrow}；点击未展开=${!couponPanel}`
      );
    }
    await page.setData({
      availableCoupons: previousCoupons,
      showCouponPanel: previousCouponPanel
    });
    if (seededCheckoutItems) {
      await page.setData({ isLoggedIn: previousLoggedIn, checkoutItems: previousItems });
    }
  }

  if (pageDef.path === "pages/chat/index") {
    const data = await page.data();
    const previousChatState = {
      canUseChat: Boolean(data.canUseChat),
      canSendMessage: Boolean(data.canSendMessage),
      sending: Boolean(data.sending),
    };
    const chatEmptyIcon = await page.$(".empty-login__icon");
    if (chatEmptyIcon) {
      const iconText = (await chatEmptyIcon.text()).trim();
      const iconBackground = (await chatEmptyIcon.style("background-image")) || "";
      const iconSize = await chatEmptyIcon.size();
      const iconAriaHidden = await chatEmptyIcon.attribute("aria-hidden");
      audit.details.push(`客服登录空态图标=${Math.round(iconSize.width)}x${Math.round(iconSize.height)}px，背景=${iconBackground === "none" ? "无" : "有"}`);
      if (iconText) {
        audit.errors.push(`客服登录空态不得用文字充当图标：${iconText}`);
      }
      if (!iconBackground || iconBackground === "none") {
        audit.errors.push("客服登录空态图标缺少可渲染背景图");
      }
      if (iconSize.width < 32 || iconSize.height < 32) {
        audit.errors.push(`客服登录空态图标尺寸不足：${Math.round(iconSize.width)}x${Math.round(iconSize.height)}px`);
      }
      if (iconAriaHidden !== "true") {
        audit.errors.push("客服登录空态图标必须标记 aria-hidden");
      }
    }
    const seededChatState = !data.canUseChat;
    if (seededChatState) {
      await page.setData({ canUseChat: true, canSendMessage: false, sending: false });
      await sleep(300);
    }
    const send = await page.$(".send-btn");
    if (send) {
      if ((await send.attribute("disabled")) === null) {
        await page.setData({ canSendMessage: false });
        await sleep(180);
      }
      await inspectDisabledButtonStyle(send, "客服发送按钮", audit);
    }
    if (seededChatState) {
      await page.setData(previousChatState);
    } else if (send) {
      await page.setData({ canSendMessage: previousChatState.canSendMessage });
    }
  }

  if (audit.errors.length > 0) {
    audit.ok = false;
    result.errors.push(...audit.errors);
  }
}

async function verifyPage(miniProgram, pageDef, viewportWidth, screenshotPrefix = "final") {
  const result = {
    page: pageDef.path,
    type: pageDef.type,
    expectedTitle: pageDef.title,
    navigated: false,
    navbar: { ok: false },
    buttons: { count: 0, ok: true, details: [] },
    noDuplicateTitle: true,
    noOverflow: true,
    errors: [],
  };

  try {
    const page = await navigateAndWait(miniProgram, pageDef);
    result.actualPath = page.path;
    result.navigated = page.path === pageDef.path;
    if (!result.navigated) {
      result.errors.push(`Route mismatch: expected ${pageDef.path}, got ${page.path}`);
      result.passed = false;
      return result;
    }

    await inspectCommerceState(page, pageDef, result);
    await preparePageState(miniProgram, page, pageDef, result);
    await inspectSessionAndAuthState(page, pageDef, result, viewportWidth);
    await inspectCustomerFacingCopy(page, pageDef, result);
    await inspectInteractionStates(page, pageDef, result);

    const screenshotName = `${screenshotPrefix}-${pageDef.path.split("/")[1]}.png`;
    const screenshotPath = path.join(reportsDir, screenshotName);
    // 截图属证据，不是页面断言：先重试自动化抖动，仍失败只记环境阻塞，不阻断同页其余检查。
    const shot = await captureScreenshotWithRetry(miniProgram, screenshotPath);
    if (shot.ok) {
      result.screenshot = path.relative(process.cwd(), screenshotPath).replace(/\\/g, "/");
      result.screenshotAttempts = shot.attempts;
    } else {
      result.screenshotSkipped = true;
      result.screenshotAttempts = shot.attempts;
      result.screenshotError = shot.message;
    }

    if (pageDef.path === "pages/home/index") {
      await inspectHomeImageFallback(page, result);
    }
    if (pageDef.path === "pages/product-detail/index") {
      await inspectProductDetailScrollNav(page, pageDef, result);
    }
    if (pageDef.path === "pages/products/index") {
      await inspectProductsHeader(page, pageDef, result);
    }
    if (pageDef.path === "pages/profile/index") {
      await inspectProfileShortcuts(page, pageDef, result);
    }
    if (pageDef.path === "pages/checkout/index" || pageDef.path === "pages/address/index" || pageDef.path === "pages/group-registration/index") {
      await inspectFormFieldLabels(page, pageDef, result);
    }

    // 1. 检查 Navbar
    const fixedSafe = await page.$(".page-fixed-safe");
    if (!fixedSafe) {
      result.errors.push("Missing .page-fixed-safe container");
    } else {
      const fixedSafeSize = await fixedSafe.size();
      result.navbar.containerHeight = fixedSafeSize.height;
    }

    // 检查返回按钮
    const navBack = await page.$(".page-nav-back, .detail-back");
    if (navBack) {
      const backSize = await navBack.size();
      const backOffset = await navBack.offset();
      result.navbar.hasBack = true;
      result.navbar.backSize = `${backSize.width}x${backSize.height}`;
      result.navbar.backOffset = `${backOffset.left},${backOffset.top}`;
      if (backSize.width === 184 || backSize.width > 60 || backSize.width < 24) {
        result.navbar.ok = false;
        result.errors.push(`Abnormal back button size: ${backSize.width}x${backSize.height}`);
      } else {
        result.navbar.ok = true;
      }
    } else {
      result.navbar.hasBack = false;
      result.navbar.ok = TAB_BAR_PAGES.has(pageDef.path);
    }

    // 检查导航栏标题
    const navTitle = await page.$(".page-fixed-safe__title");
    if (navTitle) {
      const titleText = (await navTitle.text()).trim();
      const titleSize = await navTitle.size();
      const titleOffset = await navTitle.offset();
      result.navbar.titleText = titleText;
      result.navbar.titleSize = `${titleSize.width}x${titleSize.height}`;
      result.navbar.titleOffset = `${titleOffset.left},${titleOffset.top}`;

      // 检查双标题：页面内容区是否又出现了一模一样的 section-title
      const sectionTitles = await page.$$(".page-scroll .section-title, .page .section-title");
      for (const st of sectionTitles) {
        const text = (await st.text()).trim();
        if (text === titleText && text.length > 0) {
          result.noDuplicateTitle = false;
          result.errors.push(`Duplicate title detected in page body: "${text}" matches navbar title`);
        }
      }
    }

    // 2. 检查所有按钮
    const buttons = await page.$$("button, .primary-button, .ghost-button");
    result.buttons.count = buttons.length;
    for (let i = 0; i < buttons.length; i++) {
      const btn = buttons[i];
      const size = await btn.size();
      const offset = await btn.offset();
      const text = (await btn.text()).trim().replace(/\n/g, " ");
      const className = (await btn.attribute("class")) || "";

      const itemInfo = {
        index: i,
        text: text.slice(0, 16),
        class: className.split(" ").slice(0, 3).join(" "),
        size: `${size.width}x${size.height}`,
        offset: `${offset.left},${offset.top}`,
      };

      // 严查 184px 形变异常（除非全宽按钮）
      if (size.width === 184 && !className.includes("full-width") && viewportWidth !== 184) {
        result.buttons.ok = false;
        result.errors.push(`Button deformed by WeChat UA default width (184px): "${text}" (${className})`);
        itemInfo.deformed = true;
      }

      // 检查横向溢出
      if (offset.left + size.width > viewportWidth + 6) {
        result.noOverflow = false;
        result.errors.push(`Element overflows viewport horizontally: "${text}" right=${offset.left + size.width} > viewport=${viewportWidth}`);
        itemInfo.overflow = true;
      }

      result.buttons.details.push(itemInfo);
    }
  } catch (err) {
    result.errors.push(`Audit exception: ${err.message}`);
  }

  result.passed = result.errors.length === 0;
  return result;
}

async function captureLoggedOutStates(miniProgram, viewportWidth) {
  const originalStorage = {};
  for (const key of AUTH_STORAGE_KEYS) {
    originalStorage[key] = await miniProgram.callWxMethod("getStorageSync", key);
    await miniProgram.callWxMethod("removeStorageSync", key);
  }

  const pageDefs = ALL_15_PAGES.filter((pageDef) => [
    "pages/profile/index",
    "pages/orders/index",
    "pages/checkout/index",
    "pages/order-detail/index",
    "pages/recharge/index",
    "pages/address/index",
    "pages/coupons/index",
    "pages/points/index",
    "pages/chat/index"
  ].includes(pageDef.path));
  const results = [];

  try {
    for (const pageDef of pageDefs) {
      const result = await verifyPage(miniProgram, pageDef, viewportWidth, "final-logged-out");
      const pageData = await (await miniProgram.currentPage()).data();
      // 各页登录态字段不统一：会话视图优先，回退到页面自身的 loggedIn。
      const loggedInFlag = typeof pageData.sessionView?.loggedIn === "boolean"
        ? pageData.sessionView.loggedIn
        : (typeof pageData.loggedIn === "boolean" ? pageData.loggedIn : pageData.isLoggedIn);
      if (pageDef.path !== "pages/recharge/index" && loggedInFlag !== false) {
        result.errors.push(pageDef.path + ": 清除登录存储后页面仍显示已登录会话");
        result.passed = false;
      }
      results.push(result);
    }
  } finally {
    for (const key of AUTH_STORAGE_KEYS) {
      const value = originalStorage[key];
      if (value === undefined || value === null || value === "") {
        await miniProgram.callWxMethod("removeStorageSync", key);
      } else {
        await miniProgram.callWxMethod("setStorageSync", key, value);
      }
    }
  }

  return results;
}

async function main() {
  fs.mkdirSync(reportsDir, { recursive: true });
  console.log(`Connecting to WeChat DevTools at ${WS_ENDPOINT}...`);
  const backendHealthy = process.env.MINIAPP_ALLOW_BACKEND_DOWN === "1" || (await probeBackendHealth());
  if (!backendHealthy) {
    console.error(
      `后端健康检查未通过：${MINIAPP_API_BASE}/health。已跳过本轮审计并保留上一份报告；` +
        "请先启动本地后端，或显式设置 MINIAPP_ALLOW_BACKEND_DOWN=1 只跑纯界面断言。"
    );
    process.exit(2);
  }
  let miniProgram;
  try {
    miniProgram = await connectWithProbe();
  } catch (err) {
    // 自动化未响应时快速失败，避免整轮假失败覆盖上一份运行态证据。
    console.error(
      `开发者工具自动化未响应：${err.message}${describeEnvironmentHint()}。` +
        "已跳过本轮审计并保留上一份报告；请确认桌面已解锁、开发者工具已开启自动化端口后重跑。"
    );
    process.exit(2);
  }
  console.log("Connected to WeChat DevTools successfully!\n");

  // 预检：自动化目标必须能渲染当前项目页面，否则极可能是多实例/陈旧自动化端口；
  // 这种环境故障不能记成页面缺陷（见 ERRORS M-20260913-128）。
  let preflightRendered = false;
  for (let attempt = 0; attempt < 6 && !preflightRendered; attempt += 1) {
    try {
      await miniProgram.switchTab("/pages/home/index");
      await sleep(600);
      const current = await miniProgram.currentPage();
      const root = current ? await current.$(".page-fixed-safe") : null;
      preflightRendered = Boolean(current && current.path === "pages/home/index" && root);
    } catch (error) {
      // 预热阶段可重试，超时后统一归因为环境故障
    }
  }
  if (!preflightRendered) {
    console.error(
      "开发者工具自动化已连接，但目标实例无法渲染首页（疑似多实例或陈旧自动化端口）。" +
        "请完全退出微信开发者工具后重新以自动化端口启动再重跑，本轮不覆盖上一份报告。"
    );
    try {
      await miniProgram.disconnect();
    } catch (error) {
      console.error(`开发者工具连接断开失败：${error instanceof Error ? error.message : String(error)}`);
    }
    process.exit(2);
  }

  const sys = await miniProgram.systemInfo();
  const viewportWidth = Number(sys.windowWidth || sys.screenWidth || 390);
  console.log(`Environment: ${sys.model || sys.brand} | SDK: ${sys.SDKVersion} | WindowWidth: ${viewportWidth}px\n`);

  productDetailQueryId = await fetchFirstCatalogProductId();
  console.log(
    productDetailQueryId
      ? `商品详情取证样本：${productDetailQueryId}`
      : "商品目录为空，商品详情页将记录跳过原因\n"
  );

  console.log("逐页尝试采集截图；截图失败只记为证据阻塞，不阻断页面断言。\n");

  const results = [];
  let totalPass = 0;
  let totalFail = 0;

  for (let i = 0; i < ALL_15_PAGES.length; i++) {
    const pageDef = ALL_15_PAGES[i];
    console.log(`[${i + 1}/${ALL_15_PAGES.length}] Auditing ${pageDef.path} (${pageDef.title})...`);
    const pageResult = await verifyPage(miniProgram, pageDef, viewportWidth);
    results.push(pageResult);

    if (pageResult.passed) {
      totalPass++;
      const commerceDetail = pageResult.commerce?.details.join("；") || "未配置业务断言";
      console.log(`  -> PASS: Nav=${pageResult.navbar.ok ? "OK" : "N/A"}, Buttons=${pageResult.buttons.count} (0 deformed), Overflow=NONE, Commerce=${commerceDetail}`);
    } else {
      totalFail++;
      console.log(`  -> FAIL:`);
      for (const err of pageResult.errors) {
        console.log(`     x ${err}`);
      }
    }
  }

  console.log("\nAuditing deterministic logged-out states...");
  const loggedOutStates = await captureLoggedOutStates(miniProgram, viewportWidth);
  const loggedOutPassed = loggedOutStates.filter((result) => result.passed).length;
  const loggedOutFailed = loggedOutStates.length - loggedOutPassed;
  for (const result of loggedOutStates) {
    if (!result.passed) {
      totalFail++;
      for (const err of result.errors) {
        console.log(`  x ${err}`);
      }
    }
  }

  await miniProgram.disconnect();
  console.log("\nDisconnected from DevTools.");

  // 只要存在被跳过的截图，就区分“页面断言失败”与“环境缺证据”：两者都不算 PASS，但处置方式不同。
  const screenshotBlocked = [...results, ...loggedOutStates].some((result) => result.screenshotSkipped);
  const blockedByEnvironment = screenshotBlocked;

  const summary = {
    generatedAt: new Date().toISOString(),
    total: ALL_15_PAGES.length,
    passed: totalPass,
    failed: totalFail,
    status: totalFail > 0 ? "FAIL" : blockedByEnvironment ? "BLOCKED" : "PASS",
    blockedReason: blockedByEnvironment
      ? BLOCKED_REASON
      : "",
    pages: results,
    loggedOutPassed,
    loggedOutFailed,
    loggedOutStates,
  };

  const reportPath = path.join(reportsDir, "all-pages-devtools-audit.json");
  fs.writeFileSync(reportPath, JSON.stringify(summary, null, 2), "utf8");
  console.log(`\nAudit completed! Result: ${summary.status} (${totalPass}/${ALL_15_PAGES.length} passed)`);
  console.log(`Report written to: ${reportPath}`);

  if (summary.status === "BLOCKED") {
    console.log("页面断言未发现失败项；截图证据未生成，需在可截图环境下重跑本轮审计。");
  }
  if (summary.status !== "PASS") {
    process.exit(summary.status === "BLOCKED" ? 2 : 1);
  }
}

main().catch((err) => {
  console.error("Fatal error during audit:", err);
  process.exit(1);
});
