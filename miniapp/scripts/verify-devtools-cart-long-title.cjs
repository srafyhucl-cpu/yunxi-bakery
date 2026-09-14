const automator = require("miniprogram-automator");
const fs = require("node:fs");
const {
  captureEvidenceScreenshot,
  finalizeAuditStatus,
  exitForAuditStatus
} = require("./lib/devtools-audit-status.cjs");

const WS_ENDPOINT = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const REPORT_PATH = "reports/devtools/cart-long-title-audit.json";
const CART_STORAGE_KEY = "cartItems";
const CART_ROUTE = "pages/cart/index";
const PRODUCT_DETAIL_ROUTE = "pages/product-detail/index";
const LONG_TITLE = "树莓白色浪漫（树莓库利装饰，不是新鲜树莓，介意慎拍）小双层（上层有一层奥利奥夹心）";
const LONG_PRODUCT_ID = "6231489797";

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
  for (let index = 0; index < 12; index += 1) {
    await sleep(300);
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
    await sleep(300);
  }
  throw new Error(`等待${description}超时`);
}

async function main() {
  const report = {
    generatedAt: new Date().toISOString(),
    status: "FAIL",
    checks: [],
    errors: [],
  };
  let miniProgram;

  try {
    miniProgram = await automator.connect({ wsEndpoint: WS_ENDPOINT });
    // 先离开购物车并清空存储，确保后续读取的是本次播种的长名称商品。
    await miniProgram.switchTab("/pages/products/index");
    await sleep(400);
    await miniProgram.callWxMethod("removeStorageSync", CART_STORAGE_KEY);
    await miniProgram.callWxMethod("setStorageSync", CART_STORAGE_KEY, [
      {
        productId: LONG_PRODUCT_ID,
        title: LONG_TITLE,
        imageUrl: "",
        priceFen: 25800,
        priceText: "¥258.00",
        quantity: 1,
        stock: 20,
      },
    ]);

    const cart = await waitForPage(miniProgram, CART_ROUTE, true);
    if (cart.path !== CART_ROUTE) {
      throw new Error(`购物车路由错误：${cart.path}`);
    }
    const cartData = await waitForValue(
      async () => {
        const data = await cart.data();
        return Array.isArray(data.items) && data.items.length > 0 ? data : null;
      },
      "购物车长名称商品"
    );
    const item = await cart.$(".cart-item");
    const title = await cart.$(".cart-item .cart-title");
    const image = await cart.$(".cart-item .cart-image");
    const tag = await cart.$(".cart-item .tag");
    const stepper = await cart.$(".cart-item .cart-stepper");
    if (!item || !title || !image || !stepper) {
      throw new Error("购物车长名称商品缺少商品卡、商品名、数量控件或商品图入口");
    }
    // 库存充足且没有额外事实时不挂胶囊；胶囊只允许短标签，避免长运费口径被省略号截断。
    const healthyTagText = tag ? (await tag.text()).trim() : "";
    if (healthyTagText.length > 6) {
      throw new Error(`购物车状态胶囊文案过长会被截断：${healthyTagText}`);
    }
    report.checks.push({
      state: "cart-healthy-stock-tag",
      tagText: healthyTagText,
      tagHidden: !tag,
    });
    if (tag) {
      const tagOffset = await tag.offset();
      const tagSize = await tag.size();
      const stepperOffset = await stepper.offset();
      const stepperSize = await stepper.size();
      const tagStepperOverlapX =
        Math.min(tagOffset.left + tagSize.width, stepperOffset.left + stepperSize.width) -
        Math.max(tagOffset.left, stepperOffset.left);
      const tagStepperOverlapY =
        Math.min(tagOffset.top + tagSize.height, stepperOffset.top + stepperSize.height) -
        Math.max(tagOffset.top, stepperOffset.top);
      if (tagStepperOverlapX > 1 && tagStepperOverlapY > 1) {
        throw new Error(
          `购物车状态标签与数量控件重叠：重叠 ${tagStepperOverlapX.toFixed(1)}x${tagStepperOverlapY.toFixed(1)}px`
        );
      }
      report.checks.push({
        state: "cart-tag-stepper-separation",
        tagSize,
        stepperSize,
        overlapX: tagStepperOverlapX,
        overlapY: tagStepperOverlapY,
      });
    }
    // 低库存场景必须给出短标签，同时验证与数量控件仍不重叠。
    await miniProgram.callWxMethod("setStorageSync", CART_STORAGE_KEY, [
      {
        productId: LONG_PRODUCT_ID,
        title: LONG_TITLE,
        imageUrl: "",
        priceFen: 25800,
        priceText: "¥258.00",
        quantity: 1,
        stock: 3,
      },
    ]);
    await cart.callMethod("refreshCartData");
    const lowStockTag = await waitForValue(async () => {
      const element = await cart.$(".cart-item .tag");
      return element ? element : null;
    }, "低库存状态标签");
    const lowStockTagText = (await lowStockTag.text()).trim();
    if (lowStockTagText !== "仅余 3 件") {
      throw new Error(`低库存标签口径异常：${lowStockTagText}`);
    }
    const refreshedStepper = await cart.$(".cart-item .cart-stepper");
    const lowTagOffset = await lowStockTag.offset();
    const lowTagSize = await lowStockTag.size();
    const refreshedStepperOffset = await refreshedStepper.offset();
    const refreshedStepperSize = await refreshedStepper.size();
    const lowOverlapX =
      Math.min(lowTagOffset.left + lowTagSize.width, refreshedStepperOffset.left + refreshedStepperSize.width) -
      Math.max(lowTagOffset.left, refreshedStepperOffset.left);
    const lowOverlapY =
      Math.min(lowTagOffset.top + lowTagSize.height, refreshedStepperOffset.top + refreshedStepperSize.height) -
      Math.max(lowTagOffset.top, refreshedStepperOffset.top);
    report.checks.push({
      state: "cart-low-stock-tag",
      tagText: lowStockTagText,
      tagSize: lowTagSize,
      overlapX: lowOverlapX,
      overlapY: lowOverlapY,
    });
    if (lowOverlapX > 1 && lowOverlapY > 1) {
      throw new Error(
        `低库存标签与数量控件重叠：重叠 ${lowOverlapX.toFixed(1)}x${lowOverlapY.toFixed(1)}px`
      );
    }

    // 推荐卡必须复用首页统一动作与提示口径，不得出现裸“加入”或价格与按钮重叠。
    const recommendCards = await cart.$$(".recommend-card");
    const recommendData = (await cart.data()).recommendedProducts || [];
    if (recommendCards.length > 0) {
      const allowedLabels = new Set(["预订", "加入购物车", "查看"]);
      const samples = [];
      for (let index = 0; index < recommendCards.length; index += 1) {
        const card = recommendCards[index];
        const action = await card.$(".recommend-action");
        const hint = await card.$(".recommend-hint");
        const price = await card.$(".cart-price");
        if (!action || !hint || !price) {
          throw new Error("购物车推荐卡缺少价格、购买提示或动作按钮");
        }
        const actionText = (await action.text()).trim();
        const hintText = (await hint.text()).trim();
        const view = recommendData[index];
        if (!view) {
          throw new Error("购物车推荐卡数量多于页面数据");
        }
        if (actionText !== view.actionText) {
          throw new Error(`购物车推荐卡动作文案与数据不一致：${actionText} != ${view.actionText}`);
        }
        if (!allowedLabels.has(actionText)) {
          throw new Error(`购物车推荐卡动作文案不在统一口径内：${actionText}`);
        }
        if (hintText !== view.hintText) {
          throw new Error(`购物车推荐卡提示与数据不一致：${hintText} != ${view.hintText}`);
        }
        const hintFontSize = Number.parseFloat(await hint.style("font-size"));
        if (!Number.isFinite(hintFontSize) || hintFontSize < 11) {
          throw new Error(`购物车推荐卡购买提示字号过小：${hintFontSize}px`);
        }
        const actionOffset = await action.offset();
        const actionSize = await action.size();
        const priceOffset = await price.offset();
        const priceSize = await price.size();
        const overlapX =
          Math.min(priceOffset.left + priceSize.width, actionOffset.left + actionSize.width) -
          Math.max(priceOffset.left, actionOffset.left);
        const overlapY =
          Math.min(priceOffset.top + priceSize.height, actionOffset.top + actionSize.height) -
          Math.max(priceOffset.top, actionOffset.top);
        if (overlapX > 1 && overlapY > 1) {
          throw new Error(`购物车推荐卡价格与动作按钮重叠：${overlapX.toFixed(1)}x${overlapY.toFixed(1)}px`);
        }
        samples.push({ actionText, hintText, hintFontSize, overlapX, overlapY });
      }
      report.checks.push({ state: "cart-recommend-card-copy", count: recommendCards.length, samples });
    }

    const refreshedItem = (await cart.$(".cart-item")) || item;
    const refreshedTitle = (await cart.$(".cart-item .cart-title")) || title;
    const itemSize = await refreshedItem.size();
    const titleSize = await refreshedTitle.size();
    const lineClamp = await refreshedTitle.style("-webkit-line-clamp");
    const whiteSpace = await refreshedTitle.style("white-space");
    const titleLineHeight = Number.parseFloat(await refreshedTitle.style("line-height"));
    const titleData = cartData.items[0];
    if (titleData.title !== LONG_TITLE) {
      throw new Error(`购物车渲染了非播种商品：${titleData.title}`);
    }

    report.checks.push({
      state: "cart-long-title-layout",
      titleLength: LONG_TITLE.length,
      renderedTitle: titleData.title,
      itemSize,
      titleSize,
      lineClamp,
      whiteSpace,
      lineHeight: titleLineHeight,
    });

    if (Number(lineClamp) !== 2 || whiteSpace === "nowrap") {
      throw new Error("超长商品名未使用两行展示策略");
    }
    if (!Number.isFinite(titleLineHeight) || titleSize.height < titleLineHeight * 2 - 2) {
      throw new Error(`超长商品名两行高度不足：${titleSize.height}px / line-height ${titleLineHeight}px`);
    }
    if (titleSize.width < 180) {
      throw new Error(`超长商品名可用宽度不足：${titleSize.width}px`);
    }

    fs.mkdirSync("reports/devtools", { recursive: true });
    await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/final-cart-long-title.png");

    await refreshedTitle.tap();
    const detail = await waitForValue(
      async () => {
        const page = await miniProgram.currentPage();
        return page.path === PRODUCT_DETAIL_ROUTE ? page : null;
      },
      "购物车商品名进入商品详情"
    );
    report.checks.push({
      state: "cart-title-to-detail-navigation",
      path: detail.path,
    });

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
      try {
        await miniProgram.disconnect();
      } catch (error) {
        report.errors.push(`DevTools 连接断开失败：${error instanceof Error ? error.message : String(error)}`);
      }
    }
    fs.mkdirSync("reports/devtools", { recursive: true });
    report.status = finalizeAuditStatus(report);
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
  }

  console.log(`Cart long title audit: ${report.status}`);
  for (const check of report.checks) {
    console.log(`  - ${check.state}`);
  }
  for (const error of report.errors) {
    console.error(`  x ${error}`);
  }
  if (report.blockedReason) {
    console.log(`  ! ${report.blockedReason}`);
  }
  exitForAuditStatus(report.status);
}

main();
