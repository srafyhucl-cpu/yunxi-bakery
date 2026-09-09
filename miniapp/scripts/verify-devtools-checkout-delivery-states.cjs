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
  const warning = await page.$(".amount-warning");
  const submit = await page.$(".checkout-footer__submit");
  return {
    canSubmitOrder: data.canSubmitOrder,
    submitButtonText: data.submitButtonText,
    deliveryQuoteStatus: data.deliveryQuoteStatus,
    deliveryFeeText: data.deliveryFeeText,
    deliveryCalculating: data.deliveryCalculating,
    warningText: warning ? (await warning.text()).trim() : "",
    submitDisabled: submit ? Boolean(await submit.property("disabled")) : null
  };
}

async function applyState(page, state) {
  await page.setData({
    isLoggedIn: true,
    loginStateText: "已使用本地审计态加载结算信息",
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
      expectWarning: true,
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
      expectWarning: true,
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
      expectWarning: true,
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
      expectWarning: false,
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
      report.checks.push({ name: scenario.name, observed });

      if (observed.submitDisabled !== scenario.expectDisabled) {
        report.errors.push(scenario.name + " 提交按钮禁用态错误：" + observed.submitDisabled);
      }
      if (Boolean(observed.warningText) !== scenario.expectWarning) {
        report.errors.push(scenario.name + " 报价提示显示状态错误：" + (observed.warningText || "空"));
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
