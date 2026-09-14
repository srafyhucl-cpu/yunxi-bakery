// 展示型商品运行态审计：非卖品 / 虚拟价格 / 仅展示商品只能看，不能买。
// 覆盖三段真实链路：目录卡片不得生成下单动作，详情页不得出现数量与购买控件，
// 强制调用下单方法也不得写入购物车。
// 运行前提：本地后端健康 + 微信开发者工具自动化端口已开启（单实例，禁止并发跑多个审计）。
const automator = require("miniprogram-automator");
const fs = require("node:fs");
const {
  captureEvidenceScreenshot,
  finalizeAuditStatus,
  exitForAuditStatus,
} = require("./lib/devtools-audit-status.cjs");

const WS_ENDPOINT = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const API_BASE = process.env.MINIAPP_API_BASE || "http://127.0.0.1:7001";
const REPORT_PATH = "reports/devtools/display-only-products-audit.json";
const PRODUCTS_ROUTE = "pages/products/index";
const PRODUCT_DETAIL_ROUTE = "pages/product-detail/index";
const CART_STORAGE_KEY = "cartItems";
const SEARCH_KEYWORD = "非卖品";
// 五款展示型商品与后端读模型一一对应，数量变化必须显式复核，不能在审计里静默放行。
const EXPECTED_DISPLAY_ONLY_IDS = [
  "4487996522",
  "4589335101",
  "5552189607",
  "4589414115",
  "5552190749",
];
const FORBIDDEN_ACTION_TEXTS = ["预订", "加入购物车", "立即购买"];
const FORBIDDEN_DETAIL_TEXTS = ["加入购物车", "立即购买"];
const DETAIL_SCREENSHOT_PATH = "reports/devtools/display-only-product-detail.png";
const LIST_SCREENSHOT_PATH = "reports/devtools/evidence-display-only-list-after.png";
const DISPLAY_ONLY_PRICE_TEXT = "非卖品";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(readValue, accept, budgetMs = 6000) {
  const deadline = Date.now() + budgetMs;
  let value = await readValue();
  while (!accept(value) && Date.now() < deadline) {
    await sleep(250);
    value = await readValue();
  }
  return { ok: accept(value), value };
}

async function waitForPage(miniProgram, route, isTabPage = false) {
  const expectedRoute = route.split("?")[0];
  if (isTabPage) {
    await miniProgram.switchTab(`/${route}`);
  } else {
    await miniProgram.reLaunch(`/${route}`);
  }
  for (let index = 0; index < 12; index += 1) {
    await sleep(300);
    const page = await miniProgram.currentPage();
    if (page.path === expectedRoute) {
      return page;
    }
  }
  return miniProgram.currentPage();
}

async function fetchCatalogFromApi() {
  const items = [];
  let offset = 0;
  let total = 0;
  for (let pageIndex = 0; pageIndex < 10; pageIndex += 1) {
    const response = await fetch(
      `${API_BASE}/api/v1/miniapp/products?limit=100&offset=${offset}&sort=popular`
    );
    if (!response.ok) {
      throw new Error(`商品接口不可用：HTTP ${response.status}`);
    }
    const payload = await response.json();
    const pageItems = Array.isArray(payload?.data) ? payload.data : [];
    items.push(...pageItems);
    total = Number(payload?.meta?.total || total);
    if (!payload?.meta?.hasMore || pageItems.length === 0) {
      break;
    }
    offset += 100;
  }
  return { items, total };
}

async function readCartProductIds(miniProgram) {
  const stored = await miniProgram.callWxMethod("getStorageSync", CART_STORAGE_KEY);
  if (!Array.isArray(stored)) {
    return [];
  }
  return stored.map((item) => String(item?.productId || "")).filter(Boolean);
}

async function readSearchState(page) {
  const data = await page.data();
  return {
    searchText: String(data.searchText || ""),
    results: Array.isArray(data.globalSearchResults) ? data.globalSearchResults : [],
  };
}

// 与既有搜索审计同口径：优先真实输入注入，事件层未送达时回退到页面自身搜索方法。
async function typeKeyword(page, keyword) {
  const input = await page.$(".products-search__input");
  if (!input) {
    throw new Error("商品目录搜索框不存在");
  }
  await input.input(keyword);
  const injected = await waitFor(
    async () => readSearchState(page),
    (state) => state && state.searchText === keyword && state.results.length > 0,
    6000
  );
  if (injected.ok) {
    return { state: injected.value, inputPath: "input-injection" };
  }
  await page.callMethod("clearSearch");
  await page.callMethod("onSearchInput", { detail: { value: keyword } });
  const fallback = await waitFor(
    async () => readSearchState(page),
    (state) => state && state.searchText === keyword && state.results.length > 0,
    4000
  );
  if (!fallback.ok) {
    throw new Error(`搜索关键词未返回结果：${keyword}`);
  }
  return { state: fallback.value, inputPath: "page-method-fallback" };
}

async function readDetailState(page) {
  const data = await page.data();
  const product = data.product || null;
  const displayOnlyCard = await page.$(".detail-display-only-card");
  const quantityRow = await page.$(".detail-qty-row");
  const stepper = await page.$(".yunxi-stepper");
  const fulfillmentCard = await page.$(".detail-fulfillment-card");
  const actions = await page.$(".detail-actions");
  const detailMeta = await page.$(".detail-meta");
  const detailMain = await page.$(".detail-main");
  const mainSectionText = detailMain ? (await detailMain.text()).trim() : "";
  const relatedStrip = await page.$(".related-strip");
  const relatedText = relatedStrip ? (await relatedStrip.text()).trim() : "";
  const actionTexts = [];
  for (const button of await page.$$(".detail-actions button")) {
    actionTexts.push((await button.text()).trim());
  }
  return {
    canPurchase: Boolean(data.canPurchase),
    isDisplayOnly: Boolean(data.isDisplayOnly),
    unavailableText: String(data.unavailableText || ""),
    productId: product ? String(product.id || "") : "",
    productPurchasableFlag: product ? product.isPurchasable : null,
    displayOnlyText: displayOnlyCard ? (await displayOnlyCard.text()).trim() : "",
    hasQuantityRow: Boolean(quantityRow),
    hasStepper: Boolean(stepper),
    hasFulfillmentCard: Boolean(fulfillmentCard),
    actionText: actions ? (await actions.text()).trim() : "",
    hasDetailMeta: Boolean(detailMeta),
    mainSectionText,
    relatedText,
    actionTexts,
  };
}

async function main() {
  const report = {
    generatedAt: new Date().toISOString(),
    apiBase: API_BASE,
    status: "FAIL",
    checks: [],
    screenshots: [],
    errors: [],
  };
  let miniProgram;

  try {
    miniProgram = await automator.connect({ wsEndpoint: WS_ENDPOINT });
    await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);

    // 1. 服务端契约：展示型商品必须由读模型显式标记，且数量与预期一致。
    const catalog = await fetchCatalogFromApi();
    const displayOnlyFromApi = catalog.items.filter((item) => item.isPurchasable === false);
    const displayOnlyApiIds = displayOnlyFromApi.map((item) => String(item.id)).sort();
    const expectedIds = [...EXPECTED_DISPLAY_ONLY_IDS].sort();
    report.checks.push({
      name: "api-read-model",
      total: catalog.total,
      fetched: catalog.items.length,
      displayOnlyCount: displayOnlyFromApi.length,
      displayOnlyIds: displayOnlyApiIds,
      displayOnlyTitles: displayOnlyFromApi.map((item) => String(item.title || "")),
    });
    if (catalog.items.length !== catalog.total) {
      report.errors.push(`商品接口未翻页拉全：实际 ${catalog.items.length} / 总数 ${catalog.total}`);
    }
    if (displayOnlyApiIds.join(",") !== expectedIds.join(",")) {
      report.errors.push(
        `展示型商品集合与预期不一致：实际 [${displayOnlyApiIds.join(", ")}]，预期 [${expectedIds.join(", ")}]`
      );
    }

    // 2. 目录卡片：展示型商品只能是“查看”，不得出现任何下单动作。
    const productsPage = await waitForPage(miniProgram, PRODUCTS_ROUTE, true);
    if (productsPage.path !== PRODUCTS_ROUTE) {
      throw new Error(`商品目录页路由错误：${productsPage.path}`);
    }
    const search = await typeKeyword(productsPage, SEARCH_KEYWORD);
    const displayOnlyIds = new Set(EXPECTED_DISPLAY_ONLY_IDS);
    const searchedCards = search.state.results
      .filter((item) => displayOnlyIds.has(String(item.id)))
      .map((item) => ({
        id: String(item.id),
        title: String(item.title || ""),
        actionText: String(item.actionText || ""),
        badgeText: String(item.badgeText || ""),
        stockText: String(item.stockText || ""),
        priceText: String(item.priceText || ""),
        isUnavailable: Boolean(item.isUnavailable),
      }));
    const badActionCards = searchedCards.filter(
      (card) =>
        card.actionText !== "查看" ||
        !card.isUnavailable ||
        FORBIDDEN_ACTION_TEXTS.some((text) => card.actionText.includes(text))
    );
    const missingBadgeCards = searchedCards.filter((card) => card.badgeText !== "仅供展示");
    report.checks.push({
      name: "catalog-search-cards",
      keyword: SEARCH_KEYWORD,
      inputPath: search.inputPath,
      resultCount: search.state.results.length,
      displayOnlyCards: searchedCards,
    });
    if (searchedCards.length === 0) {
      report.errors.push(`搜索“${SEARCH_KEYWORD}”没有命中任何展示型商品，审计口径失效`);
    }
    if (badActionCards.length > 0) {
      report.errors.push(
        `展示型商品卡片仍生成下单动作：${badActionCards
          .map((card) => `${card.id}(${card.actionText})`)
          .join("、")}`
      );
    }
    if (missingBadgeCards.length > 0) {
      report.errors.push(
        `展示型商品卡片缺少“仅供展示”标签：${missingBadgeCards.map((card) => card.id).join("、")}`
      );
    }

    // 非卖品没有真实售价：同步数据里的虚拟占位价与库存文案不得出现在卡片上。
    const badPriceCards = searchedCards.filter(
      (card) => card.priceText !== DISPLAY_ONLY_PRICE_TEXT || card.priceText.includes("¥")
    );
    if (badPriceCards.length > 0) {
      report.errors.push(
        `展示型商品卡片仍展示虚拟占位价：${badPriceCards
          .map((card) => `${card.id}(${card.priceText || "空"})`)
          .join("、")}`
      );
    }
    const renderedDisplayOnlyCardTexts = [];
    for (const renderedCard of await productsPage.$$(".product-card")) {
      const cardText = (await renderedCard.text()).trim();
      if (cardText.includes(DISPLAY_ONLY_PRICE_TEXT)) {
        renderedDisplayOnlyCardTexts.push(cardText);
      }
    }
    const renderedWithFakePrice = renderedDisplayOnlyCardTexts.filter(
      (text) => text.includes("¥") || text.includes("库存充足")
    );
    report.checks.push({
      name: "catalog-search-price-render",
      displayOnlyRenderedCards: renderedDisplayOnlyCardTexts.length,
      renderedWithFakePrice,
    });
    if (renderedDisplayOnlyCardTexts.length === 0) {
      report.errors.push("搜索结果中没有渲染出“非卖品”卡片文案，价格收敛口径失效");
    }
    if (renderedWithFakePrice.length > 0) {
      report.errors.push(
        `搜索结果卡片同时出现“非卖品”与虚拟价格/库存：${renderedWithFakePrice.join(" | ")}`
      );
    }
    await captureEvidenceScreenshot(miniProgram, report, LIST_SCREENSHOT_PATH);

    // 3. 目录卡片动作：点击“查看”只跳详情，绝不能写入购物车。
    const cardIndex = search.state.results.findIndex((item) =>
      displayOnlyIds.has(String(item.id))
    );
    const actionProductId =
      cardIndex >= 0 ? String(search.state.results[cardIndex].id) : "";
    const renderedCards = await productsPage.$$(".product-card");
    if (cardIndex < 0 || !renderedCards[cardIndex]) {
      report.errors.push("展示型商品卡片未渲染，无法验证动作拦截");
    } else {
      const actionButton = await renderedCards[cardIndex].$(".product-action-btn");
      if (!actionButton) {
        report.errors.push("展示型商品卡片缺少操作按钮");
      } else {
        // 自动化点击偶发丢事件：先重试真实点击，仍不跳转才回退页面方法，并记录实际路径。
        const tapDispatchErrors = [];
        let actionPath = "tap";
        let navigated = { ok: false };
        let tapAttempts = 0;
        for (tapAttempts = 1; tapAttempts <= 3 && !navigated.ok; tapAttempts += 1) {
          try {
            await actionButton.tap();
          } catch (error) {
            tapDispatchErrors.push(error instanceof Error ? error.message : String(error));
          }
          navigated = await waitFor(
            async () => miniProgram.currentPage(),
            (page) => page.path === PRODUCT_DETAIL_ROUTE,
            3000
          );
        }
        if (!navigated.ok) {
          // 与既有搜索审计同口径：事件层未送达时直接调用页面自身动作方法。
          actionPath = "page-method-fallback";
          await productsPage.callMethod("quickAddProduct", {
            currentTarget: { dataset: { id: actionProductId } },
          });
          navigated = await waitFor(
            async () => miniProgram.currentPage(),
            (page) => page.path === PRODUCT_DETAIL_ROUTE,
            4000
          );
        }
        const cartAfterTap = await readCartProductIds(miniProgram);
        report.checks.push({
          name: "catalog-action-guard",
          actionProductId,
          actionPath,
          tapAttempts,
          tapDispatchErrors,
          navigatedToDetail: navigated.ok,
          currentRoute: (await miniProgram.currentPage()).path,
          cartProductIds: cartAfterTap,
        });
        if (!navigated.ok) {
          report.errors.push("点击展示型商品的“查看”没有进入商品详情");
        }
        if (cartAfterTap.some((id) => displayOnlyIds.has(id))) {
          report.errors.push(
            `目录卡片动作把展示型商品写入了购物车：${cartAfterTap.filter((id) => displayOnlyIds.has(id)).join("、")}`
          );
        }
      }
    }

    // 4. 详情页：无数量步进器、无履约卡、无加购与立即购买，只有返回选购与咨询客服。
    const detailPage = await waitForPage(
      miniProgram,
      `${PRODUCT_DETAIL_ROUTE}?id=${EXPECTED_DISPLAY_ONLY_IDS[1]}`
    );
    if (detailPage.path !== PRODUCT_DETAIL_ROUTE) {
      throw new Error(`商品详情页路由错误：${detailPage.path}`);
    }
    const detailReady = await waitFor(
      async () => readDetailState(detailPage),
      (state) => state.productId === EXPECTED_DISPLAY_ONLY_IDS[1],
      10000
    );
    const detail = detailReady.value;
    report.checks.push({ name: "product-detail-display-only", ...detail });
    if (detail.productId !== EXPECTED_DISPLAY_ONLY_IDS[1]) {
      report.errors.push(`详情页未加载目标展示型商品：${detail.productId}`);
    }
    if (!detail.isDisplayOnly || detail.canPurchase || detail.productPurchasableFlag !== false) {
      report.errors.push(
        `详情页未按展示型商品收敛：isDisplayOnly=${detail.isDisplayOnly}、canPurchase=${detail.canPurchase}、isPurchasable=${detail.productPurchasableFlag}`
      );
    }
    if (!detail.displayOnlyText.includes("仅供展示")) {
      report.errors.push("详情页缺少“仅供展示”说明卡");
    }
    if (detail.hasQuantityRow || detail.hasStepper) {
      report.errors.push("展示型商品详情仍展示数量步进器");
    }
    if (detail.hasFulfillmentCard) {
      report.errors.push("展示型商品详情仍展示履约与预订服务卡");
    }
    if (detail.hasDetailMeta) {
      report.errors.push("展示型商品详情仍展示“门店自提价 / 库存充足”元信息");
    }
    const detailForbiddenTexts = ["¥", "库存充足", "门店自提价"].filter((text) =>
      detail.mainSectionText.includes(text)
    );
    if (detailForbiddenTexts.length > 0) {
      report.errors.push(
        `展示型商品详情标题区仍出现价格或库存文案（${detailForbiddenTexts.join("、")}）：${detail.mainSectionText.slice(0, 80)}`
      );
    }
    if (detail.relatedText.includes("非卖品") || detail.relatedText.includes("¥99999")) {
      report.errors.push(
        `商品详情搭配推荐仍包含非卖品或虚拟占位价：${detail.relatedText.slice(0, 80)}`
      );
    }
    const forbiddenDetailTexts = FORBIDDEN_DETAIL_TEXTS.filter((text) =>
      detail.actionText.includes(text)
    );
    if (forbiddenDetailTexts.length > 0) {
      report.errors.push(`展示型商品详情底部仍出现下单动作：${forbiddenDetailTexts.join("、")}`);
    }
    if (!detail.actionText.includes("返回选购") || !detail.actionText.includes("咨询客服")) {
      report.errors.push(`展示型商品详情底部动作不完整：${detail.actionText}`);
    }

    // 5. 强制绕过页面控件直接调用下单方法：购物车必须保持为空。
    await detailPage.callMethod("addToCart");
    await detailPage.callMethod("buyNow");
    await sleep(500);
    const cartAfterDirectCalls = await readCartProductIds(miniProgram);
    report.checks.push({
      name: "forced-order-method-guard",
      cartProductIds: cartAfterDirectCalls,
      currentRoute: (await miniProgram.currentPage()).path,
    });
    if (cartAfterDirectCalls.length > 0) {
      report.errors.push(
        `强制调用下单方法仍写入购物车：${cartAfterDirectCalls.join("、")}`
      );
    }

    await captureEvidenceScreenshot(miniProgram, report, DETAIL_SCREENSHOT_PATH);
    report.status = finalizeAuditStatus(report);
  } catch (error) {
    report.errors.push(error instanceof Error ? error.message : String(error));
    report.status = finalizeAuditStatus(report);
  } finally {
    try {
      if (miniProgram) {
        await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);
      }
    } catch (error) {
      report.errors.push(
        `购物车清理失败：${error instanceof Error ? error.message : String(error)}`
      );
      report.status = "FAIL";
    }
    if (miniProgram) {
      await miniProgram.disconnect();
    }
    fs.mkdirSync("reports/devtools", { recursive: true });
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
  }

  console.log(`Display-only product audit: ${report.status}`);
  console.log(`Report written to: ${REPORT_PATH}`);
  for (const error of report.errors) {
    console.error(`  x ${error}`);
  }
  exitForAuditStatus(report.status);
}

main();
