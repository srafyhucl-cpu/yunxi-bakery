const automator = require("miniprogram-automator");
const fs = require("node:fs");

const WS_ENDPOINT = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const REPORT_PATH = "reports/devtools/checkout-delivery-state-audit.json";
const ROUTE = "pages/checkout/index";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForPage(miniProgram) {
  await miniProgram.reLaunch("/" + ROUTE);
  for (let index = 0; index < 10; index += 1) {
    await sleep(300);
    const page = await miniProgram.currentPage();
    if (page.path === ROUTE) {
      return page;
    }
  }
  return miniProgram.currentPage();
}

async function readSubmitState(page) {
  const data = await page.data();
  const guidance = await page.$(".delivery-guidance");
  const guidanceTitle = await page.$(".delivery-guidance__title");
  const guidanceText = await page.$(".delivery-guidance__text");
  const guidanceAction = await page.$(".delivery-guidance__action");
  const submit = await page.$(".checkout-footer__submit");
  return {
    canSubmitOrder: data.canSubmitOrder,
    submitButtonText: data.submitButtonText,
    deliveryQuoteStatus: data.deliveryQuoteStatus,
    deliveryFeeText: data.deliveryFeeText,
    deliveryCalculating: data.deliveryCalculating,
    guidanceVisible: Boolean(guidance),
    guidanceTitle: guidanceTitle ? (await guidanceTitle.text()).trim() : "",
    guidanceText: guidanceText ? (await guidanceText.text()).trim() : "",
    guidanceActionText: guidanceAction ? (await guidanceAction.text()).trim() : "",
    guidanceActionSize: guidanceAction ? await guidanceAction.size() : null,
    submitDisabled: submit ? Boolean(await submit.property("disabled")) : null
  };
}

async function applyState(page, state) {
  await page.setData({
    isLoggedIn: true,
    loginStateText: "已使用本地审计态加载结算信息",
    errorMessage: "",
    checkoutItems: [
      {
        productId: "delivery-state-audit",
        title: "闪送状态审计样本",
        imageUrl: "",
        priceFen: 19800,
        priceText: "¥198.00",
        quantity: 1,
      },
    ],
    receiverName: "配送审计",
    receiverPhone: "18800000001",
    deliveryType: "delivery",
    deliveryAddress: "北京市朝阳区测试路 1 号",
    selectedAddressText: "配送审计 18800000001",
    expectTime: "2026-09-10 15:00",
    goodsFen: 19800,
    goodsFenText: "¥198.00",
    totalText: "¥198.00",
    estimateCouponFenText: "-¥0.00",
    estimateRemainFenText: state.estimateRemainFenText,
    balanceDeductText: "-¥0.00",
    deliveryFeeFen: state.deliveryFeeFen,
    deliveryFeeText: state.deliveryFeeText,
    deliveryQuoteId: state.deliveryQuoteId,
    deliveryQuoteStatus: state.deliveryQuoteStatus,
    deliveryCalculating: state.deliveryCalculating,
    canSubmitOrder: state.canSubmitOrder,
    submitButtonText: state.submitButtonText,
    agreementAccepted: true,
    pendingBarVisible: false,
    submitting: false,
  });
  await page.callMethod("refreshSubmitState");
  await sleep(120);
}

async function main() {
  const report = {
    generatedAt: new Date().toISOString(),
    status: "FAIL",
    checks: [],
    errors: [],
  };
  let miniProgram;

  const scenarios = [
    {
      name: "address_required",
      state: {
        deliveryFeeFen: 0,
        deliveryFeeText: "请先填写收货地址",
        deliveryQuoteId: "",
        deliveryQuoteStatus: "address_required",
        deliveryCalculating: false,
        canSubmitOrder: false,
        submitButtonText: "先确认运费",
        estimateRemainFenText: "¥198.00",
      },
      expectDisabled: true,
      expectGuidanceTitle: "还需要补充收货信息",
      expectActionText: "完善信息",
    },
    {
      name: "quoting",
      state: {
        deliveryFeeFen: 0,
        deliveryFeeText: "确认运费中...",
        deliveryQuoteId: "",
        deliveryQuoteStatus: "quoting",
        deliveryCalculating: true,
        canSubmitOrder: false,
        submitButtonText: "先确认运费",
        estimateRemainFenText: "¥198.00",
      },
      expectDisabled: true,
      expectGuidanceTitle: "正在确认闪送运费",
      expectActionText: "",
    },
    {
      name: "expired",
      state: {
        deliveryFeeFen: 0,
        deliveryFeeText: "报价已过期",
        deliveryQuoteId: "",
        deliveryQuoteStatus: "expired",
        deliveryCalculating: false,
        canSubmitOrder: false,
        submitButtonText: "先确认运费",
        estimateRemainFenText: "¥198.00",
      },
      expectDisabled: true,
      expectGuidanceTitle: "闪送报价已过期",
      expectActionText: "重新确认",
    },
    {
      name: "address_out_of_range",
      state: {
        deliveryFeeFen: 0,
        deliveryFeeText: "当前地址超出配送范围",
        deliveryQuoteId: "",
        deliveryQuoteStatus: "address_out_of_range",
        deliveryCalculating: false,
        canSubmitOrder: false,
        submitButtonText: "先确认运费",
        estimateRemainFenText: "¥198.00",
      },
      expectDisabled: true,
      expectGuidanceTitle: "当前地址暂不支持闪送",
      expectActionText: "联系客服",
    },
    {
      name: "provider_unavailable",
      state: {
        deliveryFeeFen: 0,
        deliveryFeeText: "运费暂无法确认",
        deliveryQuoteId: "",
        deliveryQuoteStatus: "provider_unavailable",
        deliveryCalculating: false,
        canSubmitOrder: false,
        submitButtonText: "先确认运费",
        estimateRemainFenText: "¥198.00",
      },
      expectDisabled: true,
      expectGuidanceTitle: "暂时无法确认闪送费",
      expectActionText: "联系客服",
    },
    {
      name: "quoted",
      state: {
        deliveryFeeFen: 2600,
        deliveryFeeText: "¥26.00",
        deliveryQuoteId: "quote-audit-1",
        deliveryQuoteStatus: "quoted",
        deliveryCalculating: false,
        canSubmitOrder: true,
        submitButtonText: "提交订单",
        estimateRemainFenText: "¥224.00",
      },
      expectDisabled: false,
      expectGuidanceTitle: "",
      expectActionText: "",
    },
  ];

  try {
    miniProgram = await automator.connect({ wsEndpoint: WS_ENDPOINT });
    const page = await waitForPage(miniProgram);
    if (page.path !== ROUTE) {
      throw new Error("结算页路由错误：" + page.path);
    }

    for (const scenario of scenarios) {
      await applyState(page, scenario.state);
      const observed = await readSubmitState(page);
      const screenshotPath = `reports/devtools/final-checkout-state-${scenario.name}.png`;
      const scrollView = await page.$(".page-scroll");
      if (!scrollView) {
        throw new Error("结算页缺少可滚动内容区");
      }
      await scrollView.scrollTo(0, 760);
      await sleep(160);
      await miniProgram.screenshot({ path: screenshotPath });
      report.checks.push({ name: scenario.name, observed, screenshot: screenshotPath });

      if (observed.submitDisabled !== scenario.expectDisabled) {
        report.errors.push(scenario.name + " 提交按钮禁用态错误：" + observed.submitDisabled);
      }
      if (observed.guidanceTitle !== scenario.expectGuidanceTitle) {
        report.errors.push(scenario.name + " 报价指引标题错误：" + (observed.guidanceTitle || "空"));
      }
      if (observed.guidanceActionText !== scenario.expectActionText) {
        report.errors.push(scenario.name + " 恢复动作错误：" + (observed.guidanceActionText || "空"));
      }
      if (scenario.expectDisabled !== observed.guidanceVisible) {
        report.errors.push(scenario.name + " 报价指引显示状态错误");
      }
      if (observed.guidanceActionSize && (observed.guidanceActionSize.width < 44 || observed.guidanceActionSize.height < 44)) {
        report.errors.push(scenario.name + " 恢复动作触控区域过小");
      }
      if (scenario.expectDisabled && observed.submitButtonText !== "先确认运费") {
        report.errors.push(scenario.name + " 禁用态按钮文案错误：" + observed.submitButtonText);
      }
      if (!scenario.expectDisabled && observed.submitButtonText !== "提交订单") {
        report.errors.push(scenario.name + " 可提交态按钮文案错误：" + observed.submitButtonText);
      }
    }

    const quotedScenario = scenarios.find((scenario) => scenario.name === "quoted");
    await applyState(page, quotedScenario.state);
    await page.callMethod("invalidateDeliveryQuote", "quoting", "确认运费中...");
    const invalidated = await readSubmitState(page);
    report.checks.push({ name: "quote_invalidated_after_address_change", observed: invalidated });
    if (invalidated.submitDisabled !== true || invalidated.canSubmitOrder !== false) {
      report.errors.push("地址或联系人变化后旧闪送报价没有立即失效");
    }
    if (invalidated.deliveryQuoteStatus !== "quoting" || invalidated.deliveryFeeText !== "确认运费中...") {
      report.errors.push("旧报价失效后的报价状态或运费文案错误");
    }
    report.status = report.errors.length === 0 ? "PASS" : "FAIL";
  } catch (error) {
    report.errors.push(error instanceof Error ? error.message : String(error));
  } finally {
    if (miniProgram) {
      await miniProgram.disconnect();
    }
    fs.mkdirSync("reports/devtools", { recursive: true });
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
  }

  console.log("Checkout delivery state audit: " + report.status);
  console.log("Report written to: " + REPORT_PATH);
  for (const error of report.errors) {
    console.error("  x " + error);
  }
  if (report.status !== "PASS") {
    process.exit(1);
  }
}

main();
