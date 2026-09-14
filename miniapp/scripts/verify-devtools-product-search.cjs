// 商品目录搜索审计：验证搜索覆盖全量目录（不是只搜首屏）、搜索栏在输入前后不跳高、
// 清空/无结果空态/搜索结果快捷预订/结果进详情都能闭环。
// 运行前提：本地后端健康 + 微信开发者工具自动化端口已开启（单实例，禁止并发跑多个审计）。
const automator = require("miniprogram-automator");
const fs = require("node:fs");
const {
  BLOCKED_REASON,
  captureScreenshotWithRetry,
} = require("./lib/devtools-audit-status.cjs");

const WS_ENDPOINT = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const API_BASE = process.env.MINIAPP_API_BASE || "http://127.0.0.1:7001";
const REPORT_PATH = "reports/devtools/product-search-audit.json";
const PRODUCTS_ROUTE = "pages/products/index";
const PRODUCT_DETAIL_ROUTE = "pages/product-detail/index";
const CART_STORAGE_KEY = "cartItems";
// “曲奇”的全量命中都在首屏 12 款之外，用来证明长尾商品同样可搜。
// 长尾样本在目录加载后动态挑选，避免目录排序变化让固定关键词落入首屏。
// 宽口径样本用于验证搜索首屏有界渲染与增量加载到尾部（M-20260913-141）。
const BROAD_KEYWORD_CANDIDATES = ["蛋糕", "面包", "奶油", "曲奇", "自提"];
const SEARCH_RENDER_LIMIT = 30;
const EMPTY_KEYWORD = "不存在关键词zzz";
// 记录关键词写入路径：优先真实 input 注入，事件层故障时才回退到页面方法。
const inputPaths = {};
const clearPaths = {};
const MIN_TOUCH_PX = 44;
const VIEWPORT_FALLBACK_WIDTH = 390;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizeDisplayText(value) {
  return String(value || "").trim().replace(/\s+/g, "").toLocaleLowerCase();
}

// 长尾样本直接问服务端：要求命中商品全部落在目录首屏之外，避免审计口径与后端 LIKE 规则分叉。
async function pickLongTailKeyword(catalog, firstScreenIds) {
  for (const product of catalog) {
    if (firstScreenIds.includes(product.id)) {
      continue;
    }
    const title = String(product.title || "").trim();
    if (title.length < 2) {
      continue;
    }
    const page = await fetchProductPageFromApi({ keyword: title, limit: 100, offset: 0 });
    if (!page.items.length || page.total > SEARCH_RENDER_LIMIT || page.total >= catalog.length) {
      continue;
    }
    if (page.items.every((item) => !firstScreenIds.includes(item.id))) {
      return title;
    }
  }
  return "";
}

// 宽口径样本同样以服务端命中总数为准，页面只负责分页渲染。
async function pickBroadKeyword() {
  for (const keyword of BROAD_KEYWORD_CANDIDATES) {
    const page = await fetchProductPageFromApi({ keyword, limit: 1, offset: 0 });
    if (page.total > SEARCH_RENDER_LIMIT) {
      return { keyword, total: page.total };
    }
  }
  return null;
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

async function fetchProductPageFromApi({ keyword = "", limit = 100, offset = 0 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    sort: "popular"
  });
  if (keyword) {
    params.set("keyword", keyword);
  }
  const response = await fetch(`${API_BASE}/api/v1/miniapp/products?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`商品接口不可用：HTTP ${response.status}`);
  }
  const payload = await response.json();
  const meta = payload?.meta || {};
  return {
    items: Array.isArray(payload?.data) ? payload.data : [],
    total: Number(meta.total || 0),
    limit: Number(meta.limit || limit),
    offset: Number(meta.offset || offset),
    hasMore: Boolean(meta.hasMore)
  };
}

// 服务端单页上限 100：审计基准必须自己翻页拉全，不能再依赖 limit=500 的假全量。
async function fetchKeywordCatalog(keyword) {
  const items = [];
  let offset = 0;
  let total = 0;
  for (let step = 0; step < 20; step += 1) {
    const page = await fetchProductPageFromApi({ keyword, limit: 100, offset });
    items.push(...page.items);
    total = page.total;
    if (!page.hasMore) {
      break;
    }
    offset = page.offset + page.limit;
  }
  return { items, total };
}

async function fetchCatalog() {
  const catalog = await fetchKeywordCatalog("");
  if (!catalog.items.length) {
    throw new Error("全量商品接口返回空目录，无法判定搜索覆盖范围");
  }
  return catalog.items;
}

async function readSearchState(page) {
  const data = await page.data();
  const searchBar = await page.$(".products-search");
  const input = await page.$(".products-search__input");
  const clear = await page.$(".products-search__clear");
  const clears = await page.$$(".products-search__clear");
  const panel = await page.$(".products-global-search");
  const layout = await page.$(".products-layout");
  const emptyState = await page.$(".products-global-search .products-empty");
  return {
    searchText: String(data.searchText || ""),
    activeCategoryId: String(data.activeCategoryId || ""),
    activeProducts: Array.isArray(data.activeProducts) ? data.activeProducts : [],
    results: Array.isArray(data.globalSearchResults) ? data.globalSearchResults : [],
    searchMatchCount: Number(data.searchMatchCount || 0),
    searchRenderedCount: Number(data.searchRenderedCount || 0),
    searchHasMore: Boolean(data.searchHasMore),
    searchLoading: Boolean(data.searchLoading),
    searchFailed: Boolean(data.searchFailed),
    categorySections: Array.isArray(data.categorySections) ? data.categorySections : [],
    catalogTotal: Number(data.catalogTotal || 0),
    catalogOffset: Number(data.catalogOffset || 0),
    barSize: searchBar ? await searchBar.size() : null,
    barOffset: searchBar ? await searchBar.offset() : null,
    inputSize: input ? await input.size() : null,
    inputOffset: input ? await input.offset() : null,
    clearSize: clear ? await clear.size() : null,
    clearCount: clears.length,
    clearOffset: clear ? await clear.offset() : null,
    panelSize: panel ? await panel.size() : null,
    layoutSize: layout ? await layout.size() : null,
    emptyStateExists: Boolean(emptyState)
  };
}

async function typeKeyword(page, keyword, expectation) {
  const input = await page.$(".products-search__input");
  if (!input) {
    throw new Error("商品目录搜索框不存在");
  }
  await input.input(keyword);
  const injected = await waitFor(
    async () => readSearchState(page),
    (state) => state && state.searchText === keyword && expectation(state),
    6000
  );
  inputPaths[keyword] = injected.ok ? "input-injection" : "page-method-fallback";
  if (injected.ok) {
    return injected;
  }
  if (injected.value && injected.value.searchText === keyword) {
    throw new Error(
      `搜索关键词已写入但页面未按预期更新：${keyword} / 结果 ${injected.value.results.length} 条`
    );
  }

  // 开发者工具事件层未送达 bindinput 时，用页面自身方法补跑同一条搜索逻辑。
  await page.callMethod("clearSearch");
  await page.callMethod("onSearchInput", { detail: { value: keyword } });
  return waitFor(
    async () => readSearchState(page),
    (state) => state && state.searchText === keyword && expectation(state),
    4000
  );
}

async function scrollToAndVerify(page, selector, position, label) {
  const element = await page.$(selector);
  if (!element) {
    throw new Error(`${label}滚动容器不存在`);
  }
  await element.scrollTo(0, position);
  await sleep(350);
  return { element, scrollTop: Number(await element.property("scrollTop")) };
}

async function waitForScrollTop(element, accept, budgetMs = 4000) {
  return waitFor(
    async () => Number(await element.property("scrollTop")),
    accept,
    budgetMs
  );
}

async function clearByButton(page) {
  const clear = await page.$(".products-search__clear");
  if (!clear) {
    throw new Error("搜索框已有内容，但清空按钮不存在");
  }
  await clear.tap();
  const tapped = await waitFor(
    async () => readSearchState(page),
    (state) => state.searchText === "" && state.results.length === 0,
    1500
  );
  clearPaths.tap = tapped.ok ? "tap" : "page-method-fallback";
  if (tapped.ok) {
    return tapped;
  }

  // 与输入回退同理：点击事件未送达时，验证清空按钮存在后直接走页面清空方法。
  await page.callMethod("clearSearch");
  return waitFor(
    async () => readSearchState(page),
    (state) => state.searchText === "" && state.results.length === 0,
    4000
  );
}

async function main() {
  const report = {
    generatedAt: new Date().toISOString(),
    status: "FAIL",
    checks: [],
    errors: []
  };
  let screenshotBlocked = false;
  let miniProgram;

  try {
    const catalog = await fetchCatalog();
    report.catalog = { apiCount: catalog.length };

    miniProgram = await automator.connect({ wsEndpoint: WS_ENDPOINT });
    const systemInfo = await miniProgram.systemInfo();
    const viewportWidth = Number(systemInfo.windowWidth || systemInfo.screenWidth || VIEWPORT_FALLBACK_WIDTH);
    report.viewport = { width: viewportWidth, model: systemInfo.model, SDKVersion: systemInfo.SDKVersion };

    await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);

    await waitForPage(miniProgram, PRODUCTS_ROUTE, true);
    // 上一轮审计可能注入过分类夹具；强制重建页面，避免 loaded 短路复用脏状态。
    await miniProgram.reLaunch(`/${PRODUCTS_ROUTE}`);
    await sleep(800);
    const page = await miniProgram.currentPage();
    if (page.path !== PRODUCTS_ROUTE) {
      throw new Error(`商品目录路由错误：${page.path}`);
    }
    const loaded = await waitFor(
      async () => {
        const data = await page.data();
        return {
          loaded: data.loaded === true,
          activeProducts: Array.isArray(data.activeProducts) ? data.activeProducts : [],
          catalogTotal: Number(data.catalogTotal || 0),
          catalogOffset: Number(data.catalogOffset || 0),
          hasMoreProducts: Boolean(data.hasMoreProducts)
        };
      },
      (state) => state.loaded && state.activeProducts.length > 0,
      12000
    );
    if (!loaded.ok) {
      throw new Error(`商品目录未在预期时间内加载完成：${loaded.value.activeProducts.length} 款`);
    }

    // 页面只保留首屏分页数据：审计基准改为服务端第一页（limit=12 / offset=0 / sort=popular）。
    const firstPage = await fetchProductPageFromApi({ limit: 12, offset: 0 });
    const pageIds = loaded.value.activeProducts.map((product) => product.id);
    const apiIds = firstPage.items.map((product) => product.id);
    const sameOrder = pageIds.length === apiIds.length && pageIds.every((id, index) => id === apiIds[index]);
    const totalMatched = loaded.value.catalogTotal === firstPage.total;
    const offsetMatched = loaded.value.catalogOffset === firstPage.offset + firstPage.limit;
    const hasMoreMatched = loaded.value.hasMoreProducts === firstPage.hasMore;
    report.checks.push({
      state: "catalog-first-page",
      pageCount: pageIds.length,
      apiCount: apiIds.length,
      pageTotal: loaded.value.catalogTotal,
      apiTotal: firstPage.total,
      pageOffset: loaded.value.catalogOffset,
      hasMoreProducts: loaded.value.hasMoreProducts,
      sameOrder,
      totalMatched
    });
    if (!sameOrder) {
      throw new Error("商品首屏与服务端分页结果不一致，分页顺序无法据此判定");
    }
    if (!totalMatched || !offsetMatched || !hasMoreMatched) {
      throw new Error(
        `商品首屏分页元数据不一致：total ${loaded.value.catalogTotal}/${firstPage.total}，offset ${loaded.value.catalogOffset}/${firstPage.offset + firstPage.limit}，hasMore ${loaded.value.hasMoreProducts}/${firstPage.hasMore}`
      );
    }

    // 标签页会保留上一次搜索词（本身是合理行为），审计前先用页面自身的清空入口复位。
    const preReset = await readSearchState(page);
    if (preReset.searchText || preReset.clearSize) {
      await page.callMethod("clearSearch");
      const reset = await waitFor(
        async () => readSearchState(page),
        (state) => state.searchText === "" && !state.clearSize && state.results.length === 0,
        4000
      );
      if (!reset.ok) {
        throw new Error(`搜索框遗留状态无法清空：${reset.value.searchText}`);
      }
    }

    const initial = await readSearchState(page);
    report.checks.push({
      state: "search-bar-idle-geometry",
      barSize: initial.barSize,
      barOffset: initial.barOffset,
      inputSize: initial.inputSize,
      inputOffset: initial.inputOffset,
      clearCount: initial.clearCount,
      clearVisible: Boolean(initial.clearSize)
    });
    if (initial.clearSize) {
      throw new Error("搜索框为空时不应显示清空按钮");
    }
    if (initial.clearCount !== 0) {
      throw new Error(`搜索框为空时渲染了 ${initial.clearCount} 个清空按钮`);
    }
    if (!initial.barSize || initial.barSize.height <= 0) {
      throw new Error("商品目录搜索栏未渲染出高度");
    }
    const idleRight = initial.barOffset.left + initial.barSize.width;
    if (initial.barOffset.left < 0 || idleRight > viewportWidth + 0.5) {
      throw new Error(
        `搜索栏横向溢出视口：left ${initial.barOffset.left.toFixed(1)} / right ${idleRight.toFixed(1)} / 视口 ${viewportWidth}`
      );
    }

    const firstScreenIds = initial.activeProducts.map((product) => product.id);
    const longTailKeyword = await pickLongTailKeyword(catalog, firstScreenIds);
    if (!longTailKeyword) {
      throw new Error("无法从服务端目录中挑选确认不在首屏的搜索样本");
    }
    report.catalog.keyword = longTailKeyword;
    const expectedMatches = (await fetchKeywordCatalog(longTailKeyword)).items;
    if (!expectedMatches.length) {
      throw new Error(`服务端搜索返回空结果：关键词「${longTailKeyword}」，审计样本失效`);
    }
    const longTailOnly = expectedMatches.every((product) => !firstScreenIds.includes(product.id));
    report.checks.push({
      state: "search-sample",
      keyword: longTailKeyword,
      expectedCount: expectedMatches.length,
      expectedIds: expectedMatches.map((product) => product.id),
      firstScreenIds,
      longTailOnly
    });
    if (!longTailOnly) {
      throw new Error(`搜索样本「${longTailKeyword}」命中首屏商品，无法证明长尾可搜`);
    }

    const searched = await typeKeyword(
      page,
      longTailKeyword,
      (state) => state.results.length === expectedMatches.length
    );
    if (!searched.ok) {
      throw new Error(
        `搜索「${longTailKeyword}」命中条数与服务端不一致：页面 ${searched.value.results.length} 条 / 预期 ${expectedMatches.length} 条（首屏目录 ${firstScreenIds.length} 款）`
      );
    }
    const resultIds = searched.value.results.map((product) => product.id);
    const expectedIds = expectedMatches.map((product) => product.id);
    const sameResultOrder = resultIds.every((id, index) => id === expectedIds[index]);
    report.checks.push({
      state: "search-long-tail-coverage",
      keyword: longTailKeyword,
      inputPath: inputPaths[longTailKeyword] || "unknown",
      renderedCount: resultIds.length,
      resultIds,
      expectedIds,
      sameResultOrder
    });
    if (!sameResultOrder) {
      throw new Error(`搜索结果顺序与目录排序不一致：${resultIds.join(",")}`);
    }

    const typed = searched.value;
    report.checks.push({
      state: "search-bar-typed-geometry",
      barSize: typed.barSize,
      inputSize: typed.inputSize,
      clearCount: typed.clearCount,
      clearSize: typed.clearSize,
      clearOffset: typed.clearOffset,
      inputOffset: typed.inputOffset
    });
    if (!typed.clearSize) {
      throw new Error("搜索框有内容时清空按钮缺失");
    }
    if (typed.clearCount !== 1) {
      throw new Error(`搜索框有内容时清空按钮数量异常：${typed.clearCount} 个`);
    }
    const barHeightDelta = Math.abs(typed.barSize.height - initial.barSize.height);
    const inputHeightDelta = Math.abs(typed.inputSize.height - initial.inputSize.height);
    if (barHeightDelta > 1 || inputHeightDelta > 1) {
      throw new Error(
        `输入关键词后搜索栏跳高：外框 ${initial.barSize.height.toFixed(1)}→${typed.barSize.height.toFixed(1)}px，输入框 ${initial.inputSize.height.toFixed(1)}→${typed.inputSize.height.toFixed(1)}px`
      );
    }
    if (typed.clearSize.width < MIN_TOUCH_PX || typed.clearSize.height < MIN_TOUCH_PX) {
      throw new Error(
        `清空按钮触控区域过小：${typed.clearSize.width.toFixed(1)}x${typed.clearSize.height.toFixed(1)}px`
      );
    }
    const clearRight = typed.clearOffset.left + typed.clearSize.width;
    const barRight = typed.barOffset.left + typed.barSize.width;
    const inputRight = typed.inputOffset.left + typed.inputSize.width;
    if (clearRight > barRight + 0.5) {
      throw new Error(`清空按钮超出搜索框：${clearRight.toFixed(1)} > ${barRight.toFixed(1)}`);
    }
    if (typed.clearOffset.top < typed.barOffset.top - 0.5 || clearRight - typed.clearOffset.width < inputRight - 0.5) {
      throw new Error("清空按钮与输入区重叠或超出搜索栏垂直范围");
    }
    const searchPanel = await page.$(".products-global-search");
    const resultCards = await page.$$(".products-global-search .product-card");
    if (!searchPanel || resultCards.length !== expectedMatches.length) {
      throw new Error(`搜索结果卡片数量异常：${resultCards.length}`);
    }
    const panelOffset = await searchPanel.offset();
    const panelSize = await searchPanel.size();
    const layoutElement = await page.$(".products-layout");
    const layoutHiddenSize = layoutElement ? await layoutElement.size() : null;
    report.checks.push({
      state: "search-panel-layout",
      panelOffset,
      panelSize,
      resultCardCount: resultCards.length,
      layoutSizeWhileSearching: layoutHiddenSize
    });
    if (layoutHiddenSize && layoutHiddenSize.height > 1) {
      throw new Error("搜索态下分类布局仍占据可见高度，搜索面板被挤压");
    }
    fs.mkdirSync("reports/devtools", { recursive: true });
    // 截图属证据：先重试自动化抖动，仍失败只丢截图，不把整轮搜索审计判成产品缺陷。
    const shot = await captureScreenshotWithRetry(
      miniProgram,
      "reports/devtools/final-product-search-results.png"
    );
    report.checks.push({
      state: "search-results-screenshot",
      ok: shot.ok,
      attempts: shot.attempts,
      ...(shot.ok ? {} : { error: shot.message }),
    });
    if (!shot.ok) {
      screenshotBlocked = true;
    }

    const cleared = await clearByButton(page);
    if (!cleared.ok) {
      throw new Error(
        `清空搜索后未回到分类浏览：searchText「${cleared.value.searchText}」结果 ${cleared.value.results.length} 条`
      );
    }
    report.checks.push({
      state: "search-clear-restore",
      activeCategoryId: cleared.value.activeCategoryId,
      previousCategoryId: initial.activeCategoryId,
      activeProducts: cleared.value.activeProducts.length,
      previousActiveProducts: initial.activeProducts.length,
      layoutSize: cleared.value.layoutSize
    });
    if (cleared.value.activeCategoryId !== initial.activeCategoryId) {
      throw new Error(
        `清空搜索后分类被重置：${initial.activeCategoryId} → ${cleared.value.activeCategoryId}`
      );
    }
    if (cleared.value.activeProducts.length !== initial.activeProducts.length) {
      throw new Error(
        `清空搜索后商品数量变化：${initial.activeProducts.length} → ${cleared.value.activeProducts.length}`
      );
    }
    if (!cleared.value.layoutSize || cleared.value.layoutSize.height <= 1) {
      throw new Error("清空搜索后分类布局没有恢复可见高度");
    }

    // 目录规模护栏：命中上百款时首屏必须有界，且触底/查看更多能到尾部（M-20260913-141）。
    const broadSample = await pickBroadKeyword();
    if (!broadSample) {
      throw new Error("服务端没有可用于验证分页边界的宽口径关键词");
    }
    const broadState = await typeKeyword(
      page,
      broadSample.keyword,
      (state) => state.searchMatchCount === broadSample.total
    );
    if (!broadState.ok) {
      throw new Error(
        `宽口径搜索「${broadSample.keyword}」命中计数异常：页面 ${broadState.value.searchMatchCount} 条 / 预期 ${broadSample.total} 条`
      );
    }
    const bounded = broadState.value;
    if (bounded.results.length > SEARCH_RENDER_LIMIT) {
      throw new Error(`搜索首屏渲染未限量：${bounded.results.length} 张卡片`);
    }
    if (bounded.searchRenderedCount !== bounded.results.length) {
      throw new Error(
        `搜索已展示计数与实际渲染不一致：${bounded.searchRenderedCount} vs ${bounded.results.length}`
      );
    }
    const summaryCopy = (
      await Promise.all(
        (await page.$$(".products-search-summary text")).map(async (element) => (await element.text()).trim())
      )
    ).filter(Boolean);
    const totalCopy = summaryCopy.find((text) => text.includes("共找到")) || "";
    const shownCopy = summaryCopy.find((text) => text.includes("已展示")) || "";
    report.checks.push({
      state: "search-render-bound",
      keyword: broadSample.keyword,
      inputPath: inputPaths[broadSample.keyword] || "unknown",
      matchedCount: bounded.searchMatchCount,
      renderedCount: bounded.searchRenderedCount,
      domCards: bounded.results.length,
      searchHasMore: bounded.searchHasMore,
      summaryCopy
    });
    if (!totalCopy.includes(String(bounded.searchMatchCount))) {
      throw new Error(`搜索计数未展示命中总数：${summaryCopy.join(" / ")}`);
    }
    if (!shownCopy.includes(String(bounded.searchRenderedCount))) {
      throw new Error(`搜索计数未展示已展示数量：${summaryCopy.join(" / ")}`);
    }
    const boundedShot = await captureScreenshotWithRetry(
      miniProgram,
      "reports/devtools/final-product-search-bounded-render.png"
    );
    report.checks.push({
      state: "search-render-bound-screenshot",
      ok: boundedShot.ok,
      attempts: boundedShot.attempts,
      ...(boundedShot.ok ? {} : { error: boundedShot.message })
    });
    if (!boundedShot.ok) {
      screenshotBlocked = true;
    }

    const firstRenderedId = bounded.results[0] ? bounded.results[0].id : "";
    let tailState = bounded;
    let loadSteps = 0;
    while (tailState.searchHasMore && loadSteps < 40) {
      const beforeCount = tailState.results.length;
      await page.callMethod("loadMoreSearchResults");
      // 服务端分页是异步的：等到本页确实追加或明确结束，避免把在途请求误判为“加载不了更多”。
      const advanced = await waitFor(
        async () => readSearchState(page),
        (state) =>
          !state.searchLoadingMore && (state.results.length > beforeCount || !state.searchHasMore),
        6000
      );
      tailState = advanced.value;
      loadSteps += 1;
    }
    const broadExpected = await fetchKeywordCatalog(broadSample.keyword);
    const tailIds = tailState.results.map((product) => product.id);
    const expectedTailIds = broadExpected.items.map((product) => product.id);
    const sameTailOrder =
      tailIds.length === expectedTailIds.length &&
      tailIds.every((id, index) => id === expectedTailIds[index]);
    const tailCards = await page.$$(".products-global-search .product-card");
    report.checks.push({
      state: "search-load-more-tail",
      keyword: broadSample.keyword,
      steps: loadSteps,
      matchedCount: tailState.searchMatchCount,
      renderedCount: tailState.searchRenderedCount,
      domCards: tailCards.length,
      searchHasMore: tailState.searchHasMore,
      firstRenderedId,
      serverTotal: broadExpected.total,
      sameTailOrder
    });
    if (tailState.searchHasMore) {
      throw new Error("搜索结果增量加载未能在上限步骤内到达尾部");
    }
    if (!sameTailOrder) {
      throw new Error(
        `搜索结果分页结果与服务端不一致：页面 ${tailIds.length} 条 / 服务端 ${expectedTailIds.length} 条`
      );
    }
    if (tailState.results.length !== tailState.searchMatchCount) {
      throw new Error(
        `搜索结果未加载到尾部：已渲染 ${tailState.results.length} / 命中 ${tailState.searchMatchCount}`
      );
    }
    if (tailCards.length !== tailState.searchMatchCount) {
      throw new Error(`尾部渲染卡片数与命中数不一致：${tailCards.length} / ${tailState.searchMatchCount}`);
    }
    if (tailState.results[0] && tailState.results[0].id !== firstRenderedId) {
      throw new Error("搜索结果增量加载后排序基准发生变化");
    }

    const restoredAfterBroad = await clearByButton(page);
    if (!restoredAfterBroad.ok) {
      throw new Error("宽口径搜索结果无法清空回目录");
    }
    const catalogBefore = await page.data();
    const beforeProducts = Array.isArray(catalogBefore.activeProducts)
      ? catalogBefore.activeProducts
      : [];
    const beforeOffset = Number(catalogBefore.catalogOffset || 0);
    if (catalogBefore.hasMoreProducts) {
      await page.callMethod("loadMoreProducts");
      const catalogAfter = await waitFor(
        async () => {
          const data = await page.data();
          return {
            count: Array.isArray(data.activeProducts) ? data.activeProducts.length : 0,
            catalogOffset: Number(data.catalogOffset || 0),
            catalogTotal: Number(data.catalogTotal || 0),
            loadingMore: Boolean(data.loadingMore),
            hasMoreProducts: Boolean(data.hasMoreProducts)
          };
        },
        (state) => !state.loadingMore && state.count > beforeProducts.length,
        8000
      );
      report.checks.push({
        state: "catalog-scroll-load-more",
        before: beforeProducts.length,
        after: catalogAfter.ok ? catalogAfter.value.count : 0,
        catalogOffset: catalogAfter.ok ? catalogAfter.value.catalogOffset : 0,
        catalogTotal: catalogAfter.ok ? catalogAfter.value.catalogTotal : 0,
        hasMoreProducts: catalogAfter.ok ? catalogAfter.value.hasMoreProducts : null
      });
      if (!catalogAfter.ok) {
        throw new Error("目录触底加载未增加可见商品数量");
      }
      if (!(catalogAfter.value.catalogOffset > beforeOffset)) {
        throw new Error(
          `目录分页偏移未推进：before ${beforeOffset} / after ${catalogAfter.value.catalogOffset}`
        );
      }
    }

    const empty = await typeKeyword(page, EMPTY_KEYWORD, (state) => state.results.length === 0);
    if (!empty.ok) {
      throw new Error(`无结果关键词仍返回 ${empty.value.results.length} 条商品`);
    }
    // 空态元素出现后文案可能晚一帧渲染：先轮询到可见文案再断言，避免把渲染时序记成缺空态（M-20260914-013）。
    const emptyCopyDeadline = Date.now() + 5000;
    while (Date.now() < emptyCopyDeadline) {
      const probeTexts = await Promise.all(
        (await page.$$(".products-global-search .products-empty text")).map(async (element) =>
          (await element.text()).trim()
        )
      );
      if (probeTexts.some((text) => text)) {
        break;
      }
      await sleep(250);
    }
    const emptyTexts = empty.value.emptyStateExists
      ? (await page.$$(".products-global-search .products-empty text")).map(async (element) =>
          (await element.text()).trim()
        )
      : [];
    const emptyCopy = (await Promise.all(emptyTexts)).filter(Boolean);
    report.checks.push({
      state: "search-empty-state",
      keyword: EMPTY_KEYWORD,
      emptyStateExists: empty.value.emptyStateExists,
      copy: emptyCopy
    });
    if (!empty.value.emptyStateExists || emptyCopy.length === 0) {
      throw new Error("无结果搜索没有给出可见空态提示");
    }
    const emptyAction = await page.$(".products-global-search .products-empty__action");
    report.checks.push({
      state: "search-empty-state-recovery",
      hasAction: Boolean(emptyAction),
      actionText: emptyAction ? (await emptyAction.text()).trim() : ""
    });
    if (!emptyAction) {
      throw new Error("无结果空态缺少一键回到全部商品的出口");
    }

    const restored = await clearByButton(page);
    if (!restored.ok) {
      throw new Error("无结果空态下清空按钮无法恢复目录");
    }

    // 滚动偏移复位：换搜索词或换分类后必须回到顶部，避免用户看到半截列表（M-20260913-146）。
    const searchScrollTarget = await typeKeyword(
      page,
      broadSample.keyword,
      (state) => state.searchMatchCount === broadSample.total
    );
    if (!searchScrollTarget.ok) {
      throw new Error("滚动复位检查前无法重新进入宽口径搜索");
    }
    const searchScrolled = await scrollToAndVerify(
      page,
      ".products-global-search",
      900,
      "搜索结果"
    );
    if (searchScrolled.scrollTop <= 1) {
      throw new Error("搜索结果未能滚动出首屏，滚动复位断言样本失效");
    }
    const narrowed = await typeKeyword(
      page,
      longTailKeyword,
      (state) => state.results.length === expectedMatches.length
    );
    if (!narrowed.ok) {
      throw new Error("滚动复位检查中收窄关键词失败");
    }
    const searchReset = await waitForScrollTop(searchScrolled.element, (top) => top <= 1);
    report.checks.push({
      state: "search-scroll-reset-on-keyword-change",
      previousKeyword: broadSample.keyword,
      keyword: longTailKeyword,
      inputPath: inputPaths[longTailKeyword] || "unknown",
      scrollTopBefore: searchScrolled.scrollTop,
      scrollTopAfter: searchReset.value
    });
    if (!searchReset.ok) {
      throw new Error(
        `切换搜索关键词后滚动偏移未复位：${searchScrolled.scrollTop} → ${searchReset.value}`
      );
    }
    const restoredAfterScrollCheck = await clearByButton(page);
    if (!restoredAfterScrollCheck.ok) {
      throw new Error("滚动复位检查后无法清空回目录");
    }

    const catalogReady = await waitFor(
      async () => {
        const data = await page.data();
        return {
          count: Array.isArray(data.activeProducts) ? data.activeProducts.length : 0,
          single: Boolean(data.isSingleCategoryLayout),
          searchText: String(data.searchText || "")
        };
      },
      (state) => state.count > 0 && !state.searchText,
      4000
    );
    if (!catalogReady.ok) {
      const catalogRaw = await page.data();
      report.catalogDebug = {
        activeCategoryId: catalogRaw.activeCategoryId,
        categorySectionIds: (catalogRaw.categorySections || []).map((section) => section.id),
        categorySectionCounts: (catalogRaw.categorySections || []).map((section) => section.countLabel),
        activeProducts: (catalogRaw.activeProducts || []).length,
        catalogTotal: catalogRaw.catalogTotal,
        catalogOffset: catalogRaw.catalogOffset
      };
      throw new Error(`滚动复位检查前目录未恢复：${JSON.stringify(catalogReady.value)}`);
    }

    const catalogScrolled = await scrollToAndVerify(
      page,
      ".products-content",
      900,
      "商品分类列表"
    );
    if (catalogScrolled.scrollTop <= 1) {
      const catalogDebug = await page.data();
      throw new Error(
        `商品分类列表未能滚动出首屏，滚动复位断言样本失效：scrollTop=${catalogScrolled.scrollTop} / 单分类布局=${catalogDebug.isSingleCategoryLayout} / 可见商品=${catalogDebug.activeProducts ? catalogDebug.activeProducts.length : 0} / 容器高度=${JSON.stringify(await catalogScrolled.element.size())}`
      );
    }
    const catalogSections = Array.isArray(restoredAfterScrollCheck.value.categorySections)
      ? restoredAfterScrollCheck.value.categorySections
      : [];
    const currentCategoryId = restoredAfterScrollCheck.value.activeCategoryId;
    let nextCategory = catalogSections.find((section) => section.id !== currentCategoryId);
    let fixtureInjected = false;
    let fixtureCategoryId = "";
    if (!nextCategory) {
      // 后端分类接口可能暂时为空（当前环境全部分在单一类目下）。
      // 此时注入一个最小第二分类夹具，验证切换后的复位逻辑本身是否生效。
      fixtureCategoryId = "audit-scroll-reset-fixture";
      const fixtureSections = catalogSections.map((section) => ({ ...section }));
      const fixtureCount = Array.isArray(restoredAfterScrollCheck.value.activeProducts)
        ? restoredAfterScrollCheck.value.activeProducts.length
        : 0;
      if (fixtureCount === 0) {
        throw new Error("当前分类没有可用商品视图，无法构造分类切换夹具");
      }
      // 分类现在是元数据 + 服务端分页：夹具只声明一个空分类，命中 0 款也不影响复位断言。
      fixtureSections.push({
        id: fixtureCategoryId,
        title: "审计分类（夹具）",
        subtitle: "0 款",
        loaded: true,
        countLabel: "0",
        hasMatches: false
      });
      await page.setData({ categorySections: fixtureSections });
      nextCategory = { id: fixtureCategoryId };
      fixtureInjected = true;
    }
    await page.callMethod("switchCategory", {
      currentTarget: { dataset: { categoryId: nextCategory.id } }
    });
    // 切换分类后布局会重算；允许首屏内的少量像素残余，但不得保留旧列表的滚动偏移。
    const catalogReset = await waitForScrollTop(catalogScrolled.element, (top) => top <= 12);
    const anchorReset = await waitFor(
      async () => {
        const data = await page.data();
        return {
          activeCategoryId: String(data.activeCategoryId || ""),
          anchor: String(data.catalogScrollAnchor || "")
        };
      },
      (state) => state.activeCategoryId === nextCategory.id && state.anchor === "products-catalog-top",
      4000
    );
    report.checks.push({
      state: "catalog-scroll-reset-on-category-switch",
      previousCategoryId: currentCategoryId,
      categoryId: nextCategory.id,
      fixtureInjected,
      fixtureCategoryId,
      anchorReset: anchorReset.value,
      scrollTopBefore: catalogScrolled.scrollTop,
      scrollTopAfter: catalogReset.value
    });
    if (!anchorReset.ok) {
      throw new Error(
        `切换分类后未回到目录顶部锚点：${JSON.stringify(anchorReset.value)}`
      );
    }
    if (!catalogReset.ok) {
      throw new Error(
        `切换商品分类后滚动偏移未复位：${catalogScrolled.scrollTop} → ${catalogReset.value}`
      );
    }
    if (fixtureInjected) {
      // 夹具只用于验证锚点复位：用完必须真正切回原分类重新拉取，不能只改 activeCategoryId。
      await page.setData({ categorySections: catalogSections });
      await page.callMethod("switchCategory", {
        currentTarget: { dataset: { categoryId: currentCategoryId } }
      });
      const restoredCatalog = await waitFor(
        async () => {
          const data = await page.data();
          return {
            activeCategoryId: String(data.activeCategoryId || ""),
            count: Array.isArray(data.activeProducts) ? data.activeProducts.length : 0
          };
        },
        (state) => state.activeCategoryId === currentCategoryId && state.count > 0,
        6000
      );
      report.checks.push({
        state: "catalog-fixture-restore",
        currentCategoryId,
        restoredCount: restoredCatalog.value.count
      });
      if (!restoredCatalog.ok) {
        throw new Error("分类夹具清理后商品目录未恢复");
      }
    }

    const addSearch = await typeKeyword(
      page,
      longTailKeyword,
      (state) => state.results.length === expectedMatches.length
    );
    if (!addSearch.ok) {
      throw new Error("再次搜索长尾关键词失败，无法验证搜索结果快捷预订");
    }
    const target = addSearch.value.results[0];
    if (!target || !target.isActive || target.stock <= 0) {
      throw new Error(`搜索首条结果不可预订：${target ? `${target.title} / 库存 ${target.stock}` : "无结果"}`);
    }
    const targetId = target.id;
    const actionButton = await page.$(".products-global-search .product-card .product-action-btn");
    if (!actionButton) {
      throw new Error("搜索结果商品卡缺少快捷预订按钮");
    }
    const actionText = (await actionButton.text()).trim();
    await actionButton.tap();
    const cartWrite = await waitFor(
      async () => miniProgram.callWxMethod("getStorageSync", CART_STORAGE_KEY),
      (items) => Array.isArray(items) && items.some((item) => item.productId === targetId),
      4000
    );
    const cartBar = await page.$(".products-cart-bar");
    report.checks.push({
      state: "search-result-quick-add",
      actionText,
      productId: targetId,
      productTitle: target.title,
      cartItems: cartWrite.ok ? cartWrite.value : null,
      cartBarVisible: Boolean(cartBar)
    });
    if (!cartWrite.ok) {
      throw new Error(`搜索结果快捷预订未写入购物车：${target.title}`);
    }
    const added = cartWrite.value.find((item) => item.productId === targetId);
    if (!added || added.quantity !== 1) {
      throw new Error(`搜索结果快捷预订数量异常：${JSON.stringify(added)}`);
    }
    if (!cartBar || (await cartBar.size()).height <= 1) {
      throw new Error("搜索结果快捷预订后未出现预订底栏");
    }

    const titleElement = await page.$(".products-global-search .product-card .product-title");
    if (!titleElement) {
      throw new Error("搜索结果商品卡缺少标题入口");
    }
    await titleElement.tap();
    const detail = await waitFor(
      async () => {
        const current = await miniProgram.currentPage();
        return {
          path: current.path,
          productId: current.path === PRODUCT_DETAIL_ROUTE ? (await current.data()).lastProductId : ""
        };
      },
      (state) => state.path === PRODUCT_DETAIL_ROUTE,
      8000
    );
    report.checks.push({
      state: "search-result-open-detail",
      path: detail.value.path,
      productId: detail.value.productId,
      expectedProductId: targetId
    });
    if (detail.value.path !== PRODUCT_DETAIL_ROUTE) {
      throw new Error(`搜索结果进入商品详情失败，当前路由 ${detail.value.path}`);
    }
    if (detail.value.productId && detail.value.productId !== targetId) {
      throw new Error(`进入的商品详情与搜索结果不一致：${detail.value.productId} != ${targetId}`);
    }

    await miniProgram.switchTab(`/${PRODUCTS_ROUTE}`);
    await sleep(400);

    report.status = "PASS";
    report.inputPaths = inputPaths;
    report.clearPaths = clearPaths;
    // 截图失败属于环境阻塞，不能把证据缺失伪装成 PASS；页面断言失败仍为 FAIL。
    report.status = screenshotBlocked ? "BLOCKED" : "PASS";
    if (screenshotBlocked) {
      report.blockedReason = BLOCKED_REASON;
    }
  } catch (error) {
    report.errors.push(error instanceof Error ? error.message : String(error));
  } finally {
    if (miniProgram) {
      try {
        await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);
      } catch (error) {
        report.errors.push(`购物车清理失败：${error instanceof Error ? error.message : String(error)}`);
      }
      try {
        await miniProgram.disconnect();
      } catch (error) {
        report.errors.push(`DevTools 连接断开失败：${error instanceof Error ? error.message : String(error)}`);
      }
    }
    fs.mkdirSync("reports/devtools", { recursive: true });
    report.inputPaths = inputPaths;
    report.clearPaths = clearPaths;
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
  }

  console.log(`Product search audit: ${report.status}`);
  for (const check of report.checks) {
    console.log(`  - ${check.state}`);
  }
  for (const error of report.errors) {
    console.error(`  x ${error}`);
  }
  if (report.blockedReason) {
    console.log(`  ! ${report.blockedReason}`);
  }
  if (report.status === "FAIL") {
    process.exit(1);
  }
  if (report.status === "BLOCKED") {
    process.exit(2);
  }
}

main();
