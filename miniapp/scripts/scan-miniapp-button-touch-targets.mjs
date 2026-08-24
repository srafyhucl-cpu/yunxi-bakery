import fs from "node:fs";
import path from "node:path";
import automator from "miniprogram-automator";

const root = process.cwd();
const reportsRoot = path.join(root, "reports", "button-visual");
const cliPath = process.env.MINIAPP_DEVTOOLS_CLI_PATH || "D:\\微信web开发者工具\\cli.bat";
const devtoolsHttpPort = Number.parseInt(process.env.MINIAPP_DEVTOOLS_HTTP_PORT || "10701", 10);
const automatorWsEndpoint =
  process.env.MINIAPP_AUTOMATOR_WS || process.env.MINIAPP_AUTOMATOR_WS_ENDPOINT || "";
const automatorPortValue = process.env.MINIAPP_AUTOMATOR_PORT;
const automatorPort = automatorPortValue ? Number.parseInt(automatorPortValue, 10) : null;
const launchTimeoutMs = Number.parseInt(process.env.MINIAPP_AUTOMATOR_TIMEOUT_MS || "120000", 10);
const MIN_TOUCH_PX = 44;

function nowStamp() {
  return new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function fixtureProduct(id, title) {
  return {
    id,
    title,
    subtitle: "运行态按钮验收",
    imageUrl: "",
    priceFen: 23800,
    priceText: "¥238.00",
    soldText: "近期热卖",
    categoryId: "birthday-cake",
    categoryName: "生日蛋糕",
    stock: 20,
    isActive: true,
    tags: ["现做"],
    specs: ["6寸"],
    notices: ["需提前预订"],
    imageClass: "cake-cream",
    badgeText: "现做",
  };
}

const orderFixture = {
  id: "rt_o_001",
  status: "pending",
  statusText: "待确认",
  paymentStatus: "unpaid",
  paymentStatusText: "待支付",
  paymentMethodText: "未记录",
  totalFen: 23800,
  totalText: "¥238.00",
  createdAt: "2026-06-21 13:30:00",
  updatedAt: "2026-06-21 13:30:00",
  itemTitle: "父亲节健康蛋糕",
  itemCount: 1,
  receiverName: "测试用户",
  receiverPhone: "18800000000",
  deliveryType: "pickup",
  deliveryTypeText: "到店自提",
  deliveryAddress: "",
  expectTime: "2026-06-22 18:00",
  remark: "按钮验收",
  canPay: true,
  canCancel: true,
  progressText: "门店会按订单状态更新制作与配送进度。",
  itemsView: [
    {
      productId: "p_001",
      title: "父亲节健康蛋糕",
      quantity: 1,
      priceText: "¥238.00",
      subtotalText: "¥238.00",
    },
  ],
  progressSteps: [
    {
      status: "pending",
      title: "已提交",
      description: "订单已进入门店确认队列",
      timeText: "2026-06-21 13:30:00",
      note: "用户提交订单",
      state: "current",
    },
    {
      status: "confirmed",
      title: "门店确认",
      description: "确认档期、库存和履约方式",
      timeText: "",
      note: "",
      state: "todo",
    },
  ],
};

async function setStorage(miniProgram) {
  await miniProgram.evaluate(() => {
    wx.setStorageSync("cartItems", [
      {
        productId: "p_001",
        title: "父亲节健康蛋糕",
        imageUrl: "",
        priceFen: 23800,
        quantity: 1,
      },
    ]);
    wx.setStorageSync("addressBookItems", [
      {
        id: "addr_001",
        receiverName: "张三",
        receiverPhone: "18800000000",
        address: "北京市东城区",
        isDefault: true,
        updatedAt: "2026-06-21T13:00:00+08:00",
      },
      {
        id: "addr_002",
        receiverName: "李四",
        receiverPhone: "19900000000",
        address: "北京市朝阳区",
        isDefault: false,
        updatedAt: "2026-06-21T13:00:00+08:00",
      },
    ]);
  });
}

async function openPage(miniProgram, url) {
  const page = await miniProgram.reLaunch(url);
  await sleep(900);
  return page;
}

async function connectMiniProgram(report) {
  if (report.wsEndpoint) {
    return automator.connect({ wsEndpoint: report.wsEndpoint });
  }
  return automator.launch({
    cliPath,
    projectPath: root,
    timeout: report.launchTimeoutMs,
    trustProject: true,
    args: ["--port", String(report.devtoolsHttpPort)],
    ...(report.automatorPort ? { port: report.automatorPort } : {}),
  });
}

function homeBlocks() {
  return [
    {
      id: "hero",
      type: "heroCarousel",
      heroAutoplay: false,
      heroIntervalMs: 3500,
      heroItems: [
        {
          id: "hero_1",
          imageUrl: "",
          title: "按钮展示验收",
          subtitle: "主推入口触达检查",
          eyebrow: "YUNXI BAKE",
          badges: ["现做", "礼赠"],
          linkType: "product",
          linkTarget: "p_001",
        },
      ],
    },
    {
      id: "quick",
      type: "quickLinks",
      quickLinkItems: [
        { id: "products", iconText: "品", title: "全部商品", subtitle: "浏览分类", linkType: "page", linkTarget: "products" },
        { id: "cart", iconText: "购", title: "购物车", subtitle: "继续结算", linkType: "page", linkTarget: "cart" },
      ],
    },
    { id: "member", type: "membershipBanner", props: { title: "会员中心", subtitle: "查看权益", actionText: "进入" } },
    {
      id: "notice",
      type: "noticeList",
      noticeItems: [{ id: "delivery", title: "配送政策", actionText: "咨询客服", linkType: "contact", linkTarget: "" }],
    },
    {
      id: "shelf",
      type: "productShelf",
      props: { title: "运行态货架", subtitle: "按钮尺寸检查" },
      products: [fixtureProduct("p_001", "父亲节健康蛋糕")],
    },
  ];
}

const states = [
  {
    name: "home",
    url: "/pages/home/index",
    setup: (page) => page.setData({ blocks: homeBlocks(), loaded: true, loading: false }),
    selectors: [
      [".home-hero__slide", 1],
      [".home-hero__tap", 1],
      [".quick-link-card", 2],
      [".member-promo", 1],
      [".service-notice", 1],
      [".shelf-head__link", 1],
      [".product-card", 1, { allowEmptyText: true }],
    ],
  },
  {
    name: "products-search",
    url: "/pages/products/index",
    setup: (page) => {
      const products = [fixtureProduct("p_001", "父亲节健康蛋糕"), fixtureProduct("p_002", "草莓奶油蛋糕")];
      return page.setData({
        loaded: true,
        loading: false,
        searchText: "蛋糕",
        globalSearchResults: products,
        allProducts: products,
        activeCategoryTitle: "搜索结果",
        activeCategorySubtitle: "按钮验收",
        activeProducts: products,
        visibleProductCount: 2,
        hasMoreProducts: false,
      });
    },
    selectors: [
      [".products-search__clear", 1],
      [".product-card", 2],
    ],
  },
  {
    name: "products-browse",
    url: "/pages/products/index",
    setup: (page) => {
      const products = [fixtureProduct("p_001", "父亲节健康蛋糕"), fixtureProduct("p_002", "草莓奶油蛋糕")];
      const section = {
        id: "all",
        title: "全部商品",
        subtitle: "按钮验收",
        countLabel: "2",
        products,
      };
      return page.setData({
        loaded: true,
        loading: false,
        searchText: "",
        globalSearchResults: [],
        allProducts: products,
        categorySections: [section, { ...section, id: "dessert", title: "甜品台" }],
        activeCategoryId: "all",
        activeCategoryTitle: "全部商品",
        activeCategorySubtitle: "按钮验收",
        activeCategoryCountLabel: "2",
        activeSectionProducts: products,
        activeProducts: products,
        visibleProductCount: 2,
        hasMoreProducts: false,
      });
    },
    selectors: [
      [".products-toggle__item", 2],
      [".products-sidebar__item", 2],
      [".product-card", 2],
    ],
  },
  {
    name: "product-detail",
    url: "/pages/product-detail/index?id=p_001",
    selectors: [[".detail-back", 1], [".ghost-button", 1], [".primary-button", 1]],
  },
  {
    name: "checkout",
    url: "/pages/checkout/index",
    setup: (page) =>
      page.setData({
        receiverName: "测试用户",
        receiverPhone: "18800000000",
        selectedAddressText: "张三 18800000000",
        deliveryAddress: "",
        agreementAccepted: true,
      }),
    selectors: [
      [".page-nav-back", 1],
      [".delivery-tab", 2],
      [".address-picker", 1],
      [".agreement-row", 1],
      [".agreement-link", 2],
      [".submit-button", 1],
    ],
  },
  {
    name: "address-list",
    url: "/pages/address/index?mode=select",
    setup: (page) =>
      page.setData({
        mode: "select",
        editing: false,
        addresses: [
          { id: "addr_001", receiverName: "张三", receiverPhone: "18800000000", address: "北京市东城区", isDefault: true },
          { id: "addr_002", receiverName: "李四", receiverPhone: "19900000000", address: "北京市朝阳区", isDefault: false },
        ],
      }),
    selectors: [[".page-nav-back", 1], [".address-add", 1], [".address-card", 2], [".text-button", 3], [".danger", 1]],
  },
  {
    name: "orders",
    url: "/pages/orders/index",
    setup: (page) =>
      page.setData({
        allOrders: [orderFixture],
        filteredOrders: [orderFixture],
        filterTabs: [
          { key: "all", label: "全部", count: 1, selected: true },
          { key: "unpaid", label: "待支付", count: 1, selected: false },
          { key: "processing", label: "进行中", count: 1, selected: false },
          { key: "done", label: "已完成", count: 0, selected: false },
          { key: "closed", label: "已关闭", count: 0, selected: false },
        ],
        loading: false,
      }),
    selectors: [[".page-nav-back", 1], [".filter-tab", 5, { allowHorizontalOverflow: true }], [".order-card", 1], [".order-action-button", 2]],
  },
  {
    name: "order-detail",
    url: "/pages/order-detail/index?id=rt_o_001",
    setup: (page) => page.setData({ orderId: "rt_o_001", order: orderFixture, loading: false, canLoadOrder: true }),
    selectors: [[".page-nav-back", 1], [".compact-button", 1], [".ghost-button", 1], [".primary-button", 2], [".danger-button", 1]],
  },
  {
    name: "chat",
    url: "/pages/chat/index",
    setup: (page) =>
      page.setData({
        chatStatus: {
          sessionId: "s_001",
          status: "transfer_pending",
          label: "正在转接人工客服",
          description: "我们已通知人工客服，请稍候。",
          isHumanHandoff: true,
        },
        messages: [],
        canUseChat: true,
        inputValue: "想了解配送范围",
        canSendMessage: true,
        loading: false,
        errorMessage: "",
      }),
    selectors: [[".quick-question-pill", 4], [".send-btn", 1]],
  },
  {
    name: "profile",
    url: "/pages/profile/index",
    setup: (page) =>
      page.setData({
        loaded: true,
        loading: false,
        loginStateText: "已使用真实登录态进入个人中心",
        sessionView: { loggedIn: true, statusText: "已登录", name: "测试用户", actionText: "刷新" },
        memberProps: { points: 12, coupons: 2, benefitCardCount: 1, levelText: "黄金会员", cardSubtitle: "单笔充值 1000 元升级", cardValidity: "永久有效", balanceFen: 10000 },
        balanceText: "¥100.00",
        orderEntries: [
          { id: "all", title: "全部", emoji: "📦", linkType: "orders", linkTarget: "" },
          { id: "unpaid", title: "待付款", emoji: "💰", linkType: "orders", linkTarget: "unpaid" },
          { id: "processing", title: "进行中", emoji: "🍰", linkType: "orders", linkTarget: "processing" },
          { id: "done", title: "已完成", emoji: "✅", linkType: "orders", linkTarget: "done" },
        ],
        serviceItems: [
          { id: "shop-phone", title: "客服电话", emoji: "📞", linkType: "phone", linkTarget: "" },
          { id: "shop-wechat", title: "客服微信", emoji: "💬", linkType: "wechat", linkTarget: "" },
          { id: "shop-after-sales", title: "售后政策", emoji: "🛡️", linkType: "policy", linkTarget: "afterSales" },
        ],
      }),
    selectors: [
      [".order-nav-item", 4],
      [".card-action-btn", 1],
      [".service-cell", 3],
    ],
  },
];

async function sampleSelector(page, selector, expectedMinCount, options, viewportWidth) {
  const elements = await page.$$(selector);
  const samples = [];
  for (const element of elements.slice(0, 6)) {
    const [text, size, offset] = await Promise.all([
      element.text().catch(() => ""),
      element.size().catch(() => ({ width: 0, height: 0 })),
      element.offset().catch(() => ({ left: 0, top: 0 })),
    ]);
    const normalizedText = String(text || "").replace(/\s+/g, " ").trim();
    const right = Number(offset.left || 0) + Number(size.width || 0);
    samples.push({
      text: normalizedText,
      size,
      offset,
      textOk: options?.allowEmptyText || normalizedText.length > 0,
      touchOk: Number(size.width || 0) >= MIN_TOUCH_PX && Number(size.height || 0) >= MIN_TOUCH_PX,
      overflowOk: options?.allowHorizontalOverflow || (Number(offset.left || 0) >= -1 && right <= viewportWidth + 1),
    });
  }
    const visibleSamples = samples.filter((sample) => Number(sample.size.width) > 0 && Number(sample.size.height) > 0);
  const ok =
    elements.length >= expectedMinCount &&
    visibleSamples.length >= expectedMinCount &&
    visibleSamples.every((sample) => sample.textOk && sample.touchOk && sample.overflowOk);
  return {
    selector,
    expectedMinCount,
    actualCount: elements.length,
    ok,
    samples,
  };
}

async function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const report = {
    traceId: "20260621-button-touch-target-scan",
    generatedAt: new Date().toISOString(),
    status: "fail",
    projectPath: root,
    cliPath,
    devtoolsHttpPort: Number.isFinite(devtoolsHttpPort) ? devtoolsHttpPort : 10701,
    connectionMode: automatorWsEndpoint ? "connect" : "launch",
    wsEndpoint: automatorWsEndpoint,
    automatorPort: Number.isFinite(automatorPort) ? automatorPort : null,
    launchTimeoutMs: Number.isFinite(launchTimeoutMs) ? launchTimeoutMs : 120000,
    minTouchPx: MIN_TOUCH_PX,
    pages: [],
    summary: {},
    notes: [
      "This scan validates rendered text, minimum 44px touch target bounds, and obvious horizontal overflow for key controls.",
      "It uses deterministic page data and does not prove service API success paths such as order submit, pay, cancel, chat send, or address save.",
    ],
  };
  let miniProgram;
  try {
    miniProgram = await connectMiniProgram(report);
    await setStorage(miniProgram);
    const systemInfo = await miniProgram.systemInfo();
    const viewportWidth = Number(systemInfo.windowWidth || systemInfo.screenWidth || 390);
    report.environment = {
      brand: systemInfo.brand,
      model: systemInfo.model,
      platform: systemInfo.platform,
      SDKVersion: systemInfo.SDKVersion,
      viewportWidth,
    };

    for (const state of states) {
      const page = await openPage(miniProgram, state.url);
      if (state.setup) {
        await state.setup(page);
        await sleep(300);
      }
      const current = await miniProgram.currentPage();
      const selectors = [];
      for (const [selector, expectedMinCount, options] of state.selectors) {
        selectors.push(await sampleSelector(page, selector, expectedMinCount, options, viewportWidth));
      }
      report.pages.push({
        name: state.name,
        expectedUrl: state.url,
        actual: { path: current.path, query: current.query },
        ok: selectors.every((selector) => selector.ok),
        selectors,
      });
    }
  } catch (error) {
    report.error = String(error?.message || error);
    report.errorStack = String(error?.stack || "");
    report.summary = {
      pages: report.pages.length,
      selectors: report.pages.reduce((sum, page) => sum + page.selectors.length, 0),
      failures: [
        {
          page: "devtools-automator",
          selector: report.wsEndpoint
            ? `connect:${report.wsEndpoint}`
            : report.automatorPort
              ? `auto-port-${report.automatorPort}`
              : "auto-port:auto",
          error: report.error,
        },
      ],
    };
  } finally {
    if (miniProgram) {
      await miniProgram.disconnect();
    }
  }

  const failures = report.pages.flatMap((page) =>
    page.selectors
      .filter((selector) => !selector.ok)
      .map((selector) => ({ page: page.name, selector: selector.selector, samples: selector.samples }))
  );
  if (!report.summary.failures) {
    report.summary = {
      pages: report.pages.length,
      selectors: report.pages.reduce((sum, page) => sum + page.selectors.length, 0),
      failures,
    };
  }
  const allFailures = report.summary.failures || failures;
  report.status = allFailures.length ? "fail" : "pass";

  const payload = `${JSON.stringify(report, null, 2)}\n`;
  const reportPath = path.join(reportsRoot, `button-touch-targets-${nowStamp()}.json`);
  fs.writeFileSync(reportPath, payload, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "button-touch-targets-latest.json"), payload, "utf8");
  console.log(`Miniapp button touch target scan ${report.status}: ${report.summary.selectors} selectors across ${report.summary.pages} pages.`);
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    for (const failure of allFailures) {
      console.error(`- ${failure.page} ${failure.selector}${failure.error ? `: ${failure.error}` : ""}`);
    }
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exit(1);
});