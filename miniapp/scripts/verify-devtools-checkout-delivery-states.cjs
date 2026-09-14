const automator = require("miniprogram-automator");
const fs = require("node:fs");
const {
  captureEvidenceScreenshot,
  finalizeAuditStatus,
  exitForAuditStatus
} = require("./lib/devtools-audit-status.cjs");

const WS_ENDPOINT = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const REPORT_PATH = "reports/devtools/checkout-delivery-state-audit.json";
const ROUTE = "pages/checkout/index";
const SHOP_CONFIG_PATH = "miniprogram/config/shop.ts";
const AUDIT_BUSINESS_HOURS = "09:00-19:30";
const AUDIT_EXPECT_TIME = buildAuditExpectTime();

function buildAuditExpectTime() {
  // 使用北京时间明天 15:00，避免固定历史日期让选择器被页面重算后与注入值不一致。
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date());
  const values = Object.fromEntries(
    parts
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value])
  );
  const tomorrow = new Date(
    Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day) + 1)
  );
  return `${tomorrow.toISOString().slice(0, 10)} 15:00`;
}

function readCanonicalPickupAddress() {
  const source = fs.readFileSync(SHOP_CONFIG_PATH, "utf8");
  const matched = /pickupAddress:\s*"([^"]+)"/.exec(source);
  if (!matched) {
    throw new Error("未找到 miniprogram/config/shop.ts 的门店自提地址");
  }
  return matched[1];
}

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
    footerAmountNote: data.footerAmountNote,
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

async function readFormLayout(page) {
  const textarea = await page.$("textarea");
  const timeGrid = await page.$(".time-grid");
  const datePicker = await page.$(".time-grid__date");
  const dateFace = await page.$(".time-grid__date .time-picker");
  const agreementRow = await page.$(".agreement-row");
  const agreementLinks = await page.$$(".agreement-link");
  const timeChevrons = await page.$$(".time-grid .time-picker__chevron");
  const timePreview = await page.$(".time-preview");
  const sizeOf = async (element) => (element ? await element.size() : null);
  const linkSizes = [];
  for (const link of agreementLinks) {
    linkSizes.push(await link.size());
  }
  const chevronSizes = [];
  for (const chevron of timeChevrons) {
    chevronSizes.push(await chevron.size());
  }
  return {
    textarea: await sizeOf(textarea),
    timeGrid: await sizeOf(timeGrid),
    datePicker: await sizeOf(datePicker),
    dateFace: await sizeOf(dateFace),
    timeChevrons: chevronSizes,
    timePreview: await sizeOf(timePreview),
    timePreviewBackground: timePreview ? await timePreview.style("background-color") : null,
    agreementRow: await sizeOf(agreementRow),
    agreementLinks: linkSizes,
  };
}

async function applyState(page, state) {
  const deliveryType = state.deliveryType || "delivery";
  const isDelivery = deliveryType === "delivery";
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
    deliveryType,
    deliveryAddress: isDelivery ? "北京市朝阳区测试路 1 号" : "",
    selectedAddressText: isDelivery ? "配送审计 18800000001" : "",
    expectTime: AUDIT_EXPECT_TIME,
    businessHours: AUDIT_BUSINESS_HOURS,
    minuteOptions: ["00", "30"],
    goodsFen: 19800,
    goodsFenText: "¥198.00",
    totalText: "¥198.00",
    estimateCouponFenText: "-",
    estimateRemainFenText: state.estimateRemainFenText,
    balanceDeductText: "-",
    availableCoupons: [],
    selectedCouponId: "",
    pointsEnabled: false,
    pointsBalance: 0,
    balanceEnabled: false,
    balanceFen: 0,
    showCouponPanel: false,
    orderLocked: false,
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
  await page.callMethod("syncExpectTimeSchedule", AUDIT_EXPECT_TIME, AUDIT_BUSINESS_HOURS);
  await page.callMethod("refreshEstimate");
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
      await captureEvidenceScreenshot(miniProgram, report, screenshotPath);
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
      // 底栏必须说清估算金额是否已包含闪送费，避免顾客只看到总额却不知道来源。
      if (!observed.footerAmountNote) {
        report.errors.push(scenario.name + " 结算底栏缺少金额来源说明");
      } else if (scenario.name === "quoted") {
        if (observed.footerAmountNote !== "已含闪送费 ¥26.00") {
          report.errors.push(
            scenario.name + " 已报价态底栏说明错误：" + observed.footerAmountNote
          );
        }
      } else if (observed.footerAmountNote.includes("已含闪送费")) {
        report.errors.push(
          scenario.name + " 运费未确认却显示已含闪送费：" + observed.footerAmountNote
        );
      }
    }

    const quotedScenario = scenarios.find((scenario) => scenario.name === "quoted");
    const canonicalPickupAddress = readCanonicalPickupAddress();
    await applyState(page, {
      deliveryType: "pickup",
      deliveryFeeFen: 0,
      deliveryFeeText: "免运费",
      deliveryQuoteId: "",
      deliveryQuoteStatus: "not_applicable",
      deliveryCalculating: false,
      canSubmitOrder: true,
      submitButtonText: "提交订单",
      estimateRemainFenText: "¥198.00",
    });
    const pickupScrollView = await page.$(".page-scroll");
    if (pickupScrollView) {
      await pickupScrollView.scrollTo(0, 0);
      await sleep(160);
      await captureEvidenceScreenshot(miniProgram, report, "reports/devtools/final-checkout-pickup-state.png");
    }
    const pickupNotice = await page.$(".notice-sub");
    const pickupNoticeText = pickupNotice ? (await pickupNotice.text()).trim() : "";
    const pickupData = await page.data();
    const pickupSelectedHour =
      (pickupData.hourOptions || [])[pickupData.selectedHourIndex] || "";
    const pickupSelectedMinute =
      (pickupData.minuteOptions || [])[pickupData.selectedMinuteIndex] || "";
    const pickupPickerExpectTime =
      `${pickupData.selectedDateValue} ${pickupSelectedHour}:${pickupSelectedMinute}`;
    const pickupObserved = {
      pickupNoticeText,
      dataPickupAddress: pickupData.pickupAddress,
      expectTime: pickupData.expectTime,
      pickerExpectTime: pickupPickerExpectTime,
      deliveryAddress: pickupData.deliveryAddress,
      deliveryFeeFen: pickupData.deliveryFeeFen,
      deliveryFeeText: pickupData.deliveryFeeText,
      deliveryQuoteStatus: pickupData.deliveryQuoteStatus,
      estimateRemainFenText: pickupData.estimateRemainFenText,
      footerAmountNote: pickupData.footerAmountNote,
    };
    report.checks.push({
      name: "pickup_address_source",
      observed: pickupObserved,
      screenshot: "reports/devtools/final-checkout-pickup-state.png",
    });
    if (!pickupNoticeText.includes(canonicalPickupAddress)) {
      report.errors.push("结算页自提门店地址未展示真实门店地址：" + (pickupNoticeText || "空"));
    }
    if (!pickupData.pickupAddress || pickupData.pickupAddress.includes("请联系客服确认")) {
      report.errors.push("结算页自提地址仍被占位文案占用：" + (pickupData.pickupAddress || "空"));
    }
    if (pickupData.expectTime !== pickupPickerExpectTime) {
      report.errors.push(
        "自提态预约预览与选择器不一致：" +
          pickupData.expectTime +
          " / " +
          pickupPickerExpectTime
      );
    }
    if (pickupData.deliveryAddress !== "") {
      report.errors.push("自提态不应复用配送地址：" + pickupData.deliveryAddress);
    }
    if (
      pickupData.deliveryFeeFen !== 0 ||
      pickupData.deliveryFeeText !== "免运费" ||
      pickupData.deliveryQuoteStatus !== "not_applicable"
    ) {
      report.errors.push(
        "自提态运费状态错误：" +
          pickupData.deliveryFeeFen +
          " / " +
          pickupData.deliveryFeeText +
          " / " +
          pickupData.deliveryQuoteStatus
      );
    }
    if (pickupData.estimateRemainFenText !== "¥198.00") {
      report.errors.push(
        "自提态实付估算仍包含配送费：" + pickupData.estimateRemainFenText
      );
    }
    if (pickupData.footerAmountNote !== "自提价 · 免运费") {
      report.errors.push("自提态底栏金额说明错误：" + (pickupData.footerAmountNote || "空"));
    }

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
    const layout = await readFormLayout(page);
    report.checks.push({ name: "checkout_form_layout", observed: layout });
    if (!layout.textarea || layout.textarea.height < 80 || layout.textarea.height > 120) {
      report.errors.push("备注输入框高度异常：" + (layout.textarea ? layout.textarea.height : "缺失"));
    }
    if (!layout.timeGrid || !layout.datePicker || !layout.dateFace) {
      report.errors.push("结算页时间选择区域结构缺失");
    } else {
      if (layout.datePicker.width < layout.timeGrid.width * 0.9) {
        report.errors.push(
          "日期选择器未独占整行：" + layout.datePicker.width + "/" + layout.timeGrid.width
        );
      }
      if (layout.dateFace.height > 60) {
        report.errors.push("日期选择文案发生换行，高度=" + layout.dateFace.height);
      }
    }
    if (layout.timeChevrons.length !== 3) {
      report.errors.push(
        "三个时间选择器未全部渲染下拉指示：" + layout.timeChevrons.length
      );
    }
    for (const chevron of layout.timeChevrons) {
      if (!chevron || chevron.width < 3 || chevron.height < 3) {
        report.errors.push("时间选择器下拉指示不可见：" + JSON.stringify(chevron));
      }
    }
    if (
      layout.timePreviewBackground &&
      layout.timePreviewBackground !== "rgba(0, 0, 0, 0)" &&
      layout.timePreviewBackground !== "transparent"
    ) {
      report.errors.push(
        "期望时间预览不应有底色，避免与可点击选择器混淆：" + layout.timePreviewBackground
      );
    }
    // 无抵扣时必须显示占位符，不能出现“-¥0.00”这种既不是零元也不代表未使用的中间态。
    const deductionData = await page.data();
    report.checks.push({
      name: "checkout_deduction_placeholder",
      observed: {
        estimateCouponFen: deductionData.estimateCouponFen,
        estimateCouponFenText: deductionData.estimateCouponFenText,
        balanceDeductText: deductionData.balanceDeductText,
      },
    });
    if (!deductionData.estimateCouponFen && deductionData.estimateCouponFenText !== "-") {
      report.errors.push(
        "优惠券无抵扣时应显示“-”，实际：" + deductionData.estimateCouponFenText
      );
    }
    if (!deductionData.balanceEnabled && deductionData.balanceDeductText !== "-") {
      report.errors.push(
        "未启用余额抵扣时应显示“-”，实际：" + deductionData.balanceDeductText
      );
    }
    if (!layout.agreementRow) {
      report.errors.push("结算页缺少协议勾选行");
    } else if (layout.agreementRow.height > 110) {
      report.errors.push("协议勾选行高度异常：" + layout.agreementRow.height);
    }
    for (const link of layout.agreementLinks) {
      if (!link || link.width < 44 || link.height < 44) {
        report.errors.push("协议链接触控区域不足 44px：" + JSON.stringify(link));
      }
    }
    // 重新进入结算页时必须按已选时间还原三个选择器，否则显示值与实际下单时间不一致。
    await page.setData({
      businessHours: "09:00-19:30",
      minuteOptions: ["00", "30"],
      expectTime: "2026-09-11 19:30",
      selectedDateValue: "2026-09-10",
      selectedHourIndex: 0,
      selectedMinuteIndex: 0,
    });
    await page.callMethod("syncExpectTimeSchedule");
    await sleep(200);
    const scheduleData = await page.data();
    const restoredHour = (scheduleData.hourOptions || [])[scheduleData.selectedHourIndex] || "";
    const restoredMinute = (scheduleData.minuteOptions || [])[scheduleData.selectedMinuteIndex] || "";
    const restoredExpectTime = `${scheduleData.selectedDateValue} ${restoredHour}:${restoredMinute}`;
    report.checks.push({
      name: "expect_time_picker_restore",
      observed: {
        expectTime: scheduleData.expectTime,
        restoredExpectTime,
        restoredHour,
        restoredMinute,
      },
    });
    if (
      scheduleData.expectTime !== restoredExpectTime ||
      restoredHour !== "19" ||
      restoredMinute !== "30"
    ) {
      report.errors.push(
        "重新进入结算页后时间选择器与实际提交时间不一致：" +
          scheduleData.expectTime +
          " / " +
          restoredExpectTime
      );
    }
    report.status = report.errors.length === 0 ? "PASS" : "FAIL";
  } catch (error) {
    report.errors.push(error instanceof Error ? error.message : String(error));
  } finally {
    if (miniProgram) {
      await miniProgram.disconnect();
    }
    fs.mkdirSync("reports/devtools", { recursive: true });
    report.status = finalizeAuditStatus(report);
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
  }

  console.log("Checkout delivery state audit: " + report.status);
  console.log("Report written to: " + REPORT_PATH);
  for (const error of report.errors) {
    console.error("  x " + error);
  }
  if (report.blockedReason) {
    console.log("  ! " + report.blockedReason);
  }
  exitForAuditStatus(report.status);
}

main();
