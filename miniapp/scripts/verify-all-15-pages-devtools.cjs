const automator = require("d:/Project/YunxiBakery/miniapp/node_modules/miniprogram-automator");
const fs = require("node:fs");
const path = require("node:path");

const WS_ENDPOINT = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const reportsDir = "d:/Project/YunxiBakery/miniapp/reports/devtools";
const AUTH_STORAGE_KEYS = ["miniappSession", "miniappUserId"];

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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function navigateAndWait(miniProgram, pageDef) {
  const url = `/${pageDef.path}`;
  for (let attempt = 0; attempt < 3; attempt++) {
    if (TAB_BAR_PAGES.has(pageDef.path)) {
      await miniProgram.switchTab(url);
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

async function inspectCommerceState(page, pageDef, result) {
  const commerce = { ok: true, details: [], errors: [] };
  const data = await page.data();

  if (pageDef.path === "pages/home/index") {
    let shelf = await page.$(".shelf");
    let cards = await page.$$(".shelf .product-card");
    for (let attempt = 0; attempt < 6 && (!shelf || cards.length === 0); attempt++) {
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

async function inspectSessionAndAuthState(page, pageDef, result) {
  const data = await page.data();
  const sessionView = data.sessionView || {};
  const notice = await page.$(".session-notice");
  const action = await page.$(".session-notice__button");

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

  if (sessionView.loggedIn === false && [
    "pages/orders/index",
    "pages/address/index",
    "pages/order-detail/index"
  ].includes(pageDef.path)) {
    const actionText = action ? (await action.text()).trim() : "";
    if (actionText !== "去登录") {
      result.errors.push(pageDef.path + ": 未登录 CTA 应为去登录");
    }
  }

  if (pageDef.path === "pages/recharge/index" && data.loggedIn === false) {
    const loginButton = await page.$(".recharge-page .empty-panel button");
    const loginText = loginButton ? (await loginButton.text()).trim() : "";
    result.rechargeAuth = { hasLoginButton: Boolean(loginButton), loginText };
    if (loginText !== "去登录") {
      result.errors.push("pages/recharge/index: 未登录充值空态缺少去登录按钮");
    }
  }

  if (pageDef.path === "pages/address/index" && sessionView.loggedIn === false) {
    if (await page.$(".address-header") || await page.$(".address-form") || await page.$(".address-add")) {
      result.errors.push("pages/address/index: 未登录时仍展示地址业务操作");
    }
  }

  if (pageDef.path === "pages/orders/index" && sessionView.loggedIn === false) {
    if (await page.$(".filter-tabs-bar") || await page.$(".order-list")) {
      result.errors.push("pages/orders/index: 未登录时仍展示订单业务内容");
    }
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
    await inspectSessionAndAuthState(page, pageDef, result);

    const screenshotName = `${screenshotPrefix}-${pageDef.path.split("/")[1]}.png`;
    const screenshotPath = path.join(reportsDir, screenshotName);
    await miniProgram.screenshot({ path: screenshotPath });
    result.screenshot = path.relative(process.cwd(), screenshotPath).replace(/\\/g, "/");

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
    "pages/orders/index",
    "pages/order-detail/index",
    "pages/recharge/index",
    "pages/address/index"
  ].includes(pageDef.path));
  const results = [];

  try {
    for (const pageDef of pageDefs) {
      const result = await verifyPage(miniProgram, pageDef, viewportWidth, "final-logged-out");
      const sessionView = (await (await miniProgram.currentPage()).data()).sessionView || {};
      if (pageDef.path !== "pages/recharge/index" && sessionView.loggedIn !== false) {
        result.errors.push(pageDef.path + ": 清除登录存储后页面仍显示已连接会话");
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
  const miniProgram = await automator.connect({ wsEndpoint: WS_ENDPOINT });
  console.log("Connected to WeChat DevTools successfully!\n");

  const sys = await miniProgram.systemInfo();
  const viewportWidth = Number(sys.windowWidth || sys.screenWidth || 390);
  console.log(`Environment: ${sys.model || sys.brand} | SDK: ${sys.SDKVersion} | WindowWidth: ${viewportWidth}px\n`);

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

  const summary = {
    generatedAt: new Date().toISOString(),
    total: ALL_15_PAGES.length,
    passed: totalPass,
    failed: totalFail,
    status: totalFail === 0 ? "PASS" : "FAIL",
    pages: results,
    loggedOutPassed,
    loggedOutFailed,
    loggedOutStates,
  };

  const reportPath = path.join(reportsDir, "all-pages-devtools-audit.json");
  fs.writeFileSync(reportPath, JSON.stringify(summary, null, 2), "utf8");
  console.log(`\nAudit completed! Result: ${summary.status} (${totalPass}/${ALL_15_PAGES.length} passed)`);
  console.log(`Report written to: ${reportPath}`);

  if (totalFail > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("Fatal error during audit:", err);
  process.exit(1);
});
