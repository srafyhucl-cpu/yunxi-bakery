const automator = require("miniprogram-automator");
const fs = require("node:fs");
const {
  captureEvidenceScreenshot,
  finalizeAuditStatus,
  exitForAuditStatus
} = require("./lib/devtools-audit-status.cjs");

const WS_ENDPOINT = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const API_BASE_URL = process.env.MINIAPP_API_BASE_URL || "http://127.0.0.1:7001";
const REPORT_PATH = "reports/devtools/registration-policy-audit.json";
const REGISTRATION_ROUTE = "pages/group-registration/index";
const POLICY_ROUTE = "pages/policy/index";
const HOME_ROUTE = "pages/home/index";
// 微信与 iOS HIG 的最小可点区域为 44px，低于该值即记录为触控目标缺陷。
const MIN_TOUCH_TARGET = 44;
const GROUP_NAME = "芸熙烘焙客户群";
const QUERY_PRODUCT_NAME = "审计商品";

const POLICY_VARIANTS = [
  {
    type: "privacy",
    titleKey: "privacyPolicyTitle",
    contentKey: "privacyPolicyContent",
    screenshot: "reports/devtools/final-policy-privacy.png",
  },
  {
    type: "agreement",
    titleKey: "userAgreementTitle",
    contentKey: "userAgreementContent",
    screenshot: "reports/devtools/final-policy-agreement.png",
  },
  {
    type: "afterSales",
    titleKey: "afterSalesPolicyTitle",
    contentKey: "afterSalesPolicyContent",
    screenshot: "reports/devtools/final-policy-after-sales.png",
  },
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function addCheck(report, name, passed, data, error) {
  report.checks.push({ name, passed, ...data });
  if (!passed) {
    report.errors.push(error);
  }
}

async function measure(element) {
  if (!element) {
    return null;
  }
  const size = await element.size();
  const offset = await element.offset();
  const width = Number(size.width);
  const height = Number(size.height);
  const top = Number(offset.top);
  return {
    width,
    height,
    left: Number(offset.left),
    top,
    bottom: top + height,
  };
}

async function waitForRoute(miniProgram, route, query = "") {
  await miniProgram.reLaunch(`/${route}${query}`);
  for (let index = 0; index < 12; index += 1) {
    await sleep(320);
    const page = await miniProgram.currentPage();
    if (page.path === route) {
      return page;
    }
  }
  return miniProgram.currentPage();
}

async function waitForData(page, predicate, description) {
  for (let index = 0; index < 15; index += 1) {
    const data = await page.data();
    if (predicate(data)) {
      return data;
    }
    await sleep(140);
  }
  throw new Error(`等待页面状态更新超时：${description}`);
}

async function readWindowInfo(miniProgram) {
  return miniProgram.evaluate(() => {
    const info = wx.getWindowInfo();
    return {
      windowWidth: info.windowWidth,
      windowHeight: info.windowHeight,
      safeAreaBottom: info.safeArea ? info.safeArea.bottom : info.windowHeight,
      statusBarHeight: info.statusBarHeight,
    };
  });
}

async function captureScreenshot(miniProgram, report, path) {
  return captureEvidenceScreenshot(miniProgram, report, path);
}

async function fetchShopSettings(report) {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/miniapp/shop-settings`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    return payload && payload.data ? payload.data : null;
  } catch (error) {
    report.errors.push(
      `读取运营配置失败（${API_BASE_URL}）：${error instanceof Error ? error.message : String(error)}`
    );
    return null;
  }
}

async function readRegistrationStructure(page) {
  const data = await page.data();
  const heroKicker = await page.$(".registration-kicker");
  const heroCopy = await page.$(".registration-copy");
  const sessionNotice = await page.$("session-notice");
  return {
    campaignId: data.campaignId,
    groupName: data.groupName,
    productName: data.productName,
    fulfillmentMethod: data.fulfillmentMethod,
    canSubmitRegistration: data.canSubmitRegistration,
    loginStateText: data.loginStateText,
    kickerText: heroKicker ? (await heroKicker.text()).trim() : "",
    copyText: heroCopy ? (await heroCopy.text()).trim() : "",
    sessionNoticeVisible: Boolean(sessionNotice),
  };
}

async function readRegistrationTouchTargets(page) {
  const inputs = await page.$$("input");
  const pickers = await page.$$("picker");
  const tabs = await page.$$(".fulfillment-tab");
  const submit = await page.$(".submit-button");
  const navBack = await page.$(".page-nav-back");
  const collection = { inputs: [], pickers: [], tabs: [] };
  for (const input of inputs) {
    collection.inputs.push(await measure(input));
  }
  for (const picker of pickers) {
    collection.pickers.push(await measure(picker));
  }
  for (const tab of tabs) {
    collection.tabs.push(await measure(tab));
  }
  collection.submit = await measure(submit);
  collection.navBack = await measure(navBack);
  return collection;
}

function findUndersizedTargets(targets) {
  const undersized = [];
  const record = (name, item) => {
    if (item && (item.height < MIN_TOUCH_TARGET || item.width < MIN_TOUCH_TARGET)) {
      undersized.push({ name, width: item.width, height: item.height });
    }
  };
  targets.inputs.forEach((item, index) => record(`input_${index}`, item));
  targets.pickers.forEach((item, index) => record(`picker_${index}`, item));
  targets.tabs.forEach((item, index) => record(`fulfillment_tab_${index}`, item));
  record("submit", targets.submit);
  record("nav_back", targets.navBack);
  return undersized;
}

async function readSubmitFeedback(page) {
  const data = await page.data();
  const error = await page.$(".registration-error");
  return {
    errorMessage: data.errorMessage,
    errorVisible: Boolean(error),
    errorText: error ? (await error.text()).trim() : "",
    submitted: data.submitted,
    submitting: data.submitting,
  };
}

async function tapSubmit(page) {
  const submit = await page.$(".submit-button");
  if (!submit) {
    throw new Error("群内登记页缺少提交按钮");
  }
  await submit.tap();
  await sleep(320);
  return readSubmitFeedback(page);
}

async function runRegistrationAudit(miniProgram, report, windowInfo) {
  const query = `?campaignId=${encodeURIComponent(
    "devtools-registration-audit"
  )}&groupName=${encodeURIComponent(GROUP_NAME)}&productName=${encodeURIComponent(QUERY_PRODUCT_NAME)}`;
  const page = await waitForRoute(miniProgram, REGISTRATION_ROUTE, query);
  if (page.path !== REGISTRATION_ROUTE) {
    throw new Error(`群内登记页路由错误：${page.path}`);
  }

  const structure = await readRegistrationStructure(page);
  addCheck(
    report,
    "registration_structure",
    structure.campaignId === "devtools-registration-audit" &&
      structure.groupName === GROUP_NAME &&
      structure.productName === QUERY_PRODUCT_NAME &&
      structure.copyText.includes("门店客服确认") &&
      structure.sessionNoticeVisible,
    { structure },
    "群内登记页未按链接参数渲染活动、商品或客服确认说明"
  );
  await captureScreenshot(miniProgram, report, "reports/devtools/final-registration-form-top.png");

  const scrollView = await page.$(".page-scroll");
  if (!scrollView) {
    throw new Error("群内登记页缺少可滚动内容区");
  }
  const contentHeight = Number(await scrollView.scrollHeight());
  const submitBeforeScroll = await measure(await page.$(".submit-button"));
  await scrollView.scrollTo(0, contentHeight);
  await sleep(240);
  const submitAfterScroll = await measure(await page.$(".submit-button"));
  const navBar = await measure(await page.$(".page-fixed-safe"));
  const safeAreaBottom = windowInfo.safeAreaBottom;
  const ctaReachable =
    submitAfterScroll &&
    submitAfterScroll.top >= (navBar ? navBar.bottom : 0) &&
    submitAfterScroll.bottom <= safeAreaBottom;
  addCheck(
    report,
    "registration_cta_reachability",
    Boolean(ctaReachable),
    {
      contentHeight,
      viewportHeight: windowInfo.windowHeight,
      safeAreaBottom,
      submitBeforeScroll,
      submitAfterScroll,
      navBar,
    },
    `群内登记页提交按钮滚到底部后仍不可完整点击：${JSON.stringify(submitAfterScroll)}`
  );
  await captureScreenshot(miniProgram, report, "reports/devtools/final-registration-form-bottom.png");

  const touchTargets = await readRegistrationTouchTargets(page);
  const undersized = findUndersizedTargets(touchTargets);
  addCheck(
    report,
    "registration_touch_targets",
    undersized.length === 0,
    { minimum: MIN_TOUCH_TARGET, targets: touchTargets, undersized },
    `群内登记页存在小于 ${MIN_TOUCH_TARGET}px 的触控目标：${JSON.stringify(undersized)}`
  );

  const pickers = await page.$$("picker");

  // 未登录时提交按钮按设计禁用；此时页面已滚到底部，可确认它不会伪提交。
  const anonymousSubmit = await page.$(".submit-button");
  // 微信登录态无法在开发工具内稳定复现，这里注入未登录字段固定闸门行为。
  await page.setData({
    canSubmitRegistration: false,
    loginStateText: "请先登录后提交群内登记，避免登记记录无法归属到你",
    loginActionText: "去登录",
    sessionView: {
      userId: "",
      openid: "",
      statusText: "微信身份",
      badgeText: "未登录",
      hintText: "登录后可查询订单和会员资产",
      actionText: "去登录",
      loggedIn: false
    }
  });
  await waitForData(page, (data) => data.canSubmitRegistration === false, "未登录态注入");
  const anonymousDisabledAttribute = anonymousSubmit
    ? await anonymousSubmit.attribute("disabled")
    : null;
  const anonymousTapFeedback = await tapSubmit(page);
  const anonymousGate = {
    canSubmitRegistration: structure.canSubmitRegistration,
    loginStateText: structure.loginStateText,
    loginActionText: (await page.data()).loginActionText,
    disabledAttribute: anonymousDisabledAttribute,
    tapFeedback: anonymousTapFeedback,
    tapBlocked:
      !anonymousTapFeedback.submitted && !anonymousTapFeedback.submitting,
  };
  const anonymousDisabledFromAttribute =
    typeof anonymousDisabledAttribute === "string" &&
    anonymousDisabledAttribute !== "false";
  const anonymousState = await page.data();
  anonymousGate.stateSource = "state-injected";
  anonymousGate.ambientLoggedIn = structure.canSubmitRegistration === true;
  anonymousGate.canSubmitRegistration = anonymousState.canSubmitRegistration;
  anonymousGate.loginStateText = anonymousState.loginStateText;
  anonymousGate.loginActionText = anonymousState.loginActionText;
  anonymousGate.disabledFromAttribute = anonymousDisabledFromAttribute;
  const anonymousGateExplained =
    anonymousDisabledFromAttribute ||
    anonymousTapFeedback.errorMessage.includes("请先登录");
  addCheck(
    report,
    "registration_anonymous_gate",
    anonymousGate.canSubmitRegistration === false &&
      anonymousGate.tapBlocked &&
      anonymousGateExplained &&
      anonymousGate.loginStateText.includes("请先登录") &&
      anonymousGate.loginActionText === "去登录",
    anonymousGate,
    "未登录访问群内登记页时提交按钮未阻断提交或缺少登录引导"
  );

  if (pickers.length !== 3) {
    throw new Error(`群内登记页时间选择器数量异常：${pickers.length}`);
  }
  const datePicker = pickers[0];
  const hourPicker = pickers[1];
  const minutePicker = pickers[2];
  const beforePickerData = await page.data();
  const expectedFutureDate = (() => {
    const [year, month, day] = String(beforePickerData.selectedDateValue)
      .split("-")
      .map(Number);
    const future = new Date(Date.UTC(year, month - 1, day + 2));
    return future.toISOString().slice(0, 10);
  })();
  await datePicker.trigger("change", { value: expectedFutureDate });
  await waitForData(
    page,
    (data) => data.selectedDateValue === expectedFutureDate,
    "日期选择器切换"
  );
  const afterDate = await page.data();
  await hourPicker.trigger("change", { value: 3 });
  await waitForData(page, (data) => data.selectedHourIndex === 3, "小时选择器切换");
  const afterHour = await page.data();
  await minutePicker.trigger("change", { value: 1 });
  await waitForData(page, (data) => data.selectedMinuteIndex === 1, "分钟选择器切换");
  const afterMinute = await page.data();
  const pickerResult = {
    expectedFutureDate,
    dateValue: afterDate.selectedDateValue,
    dateDesiredTime: afterDate.desiredTime,
    dateHourOptions: (afterDate.hourOptions || []).slice(0, 4),
    isSameDayAfterFutureDate: afterDate.isSameDayRegistration,
    hourIndex: afterHour.selectedHourIndex,
    hourDesiredTime: afterHour.desiredTime,
    minuteIndex: afterMinute.selectedMinuteIndex,
    minuteDesiredTime: afterMinute.desiredTime,
  };
  addCheck(
    report,
    "registration_time_pickers",
    pickerResult.dateValue === expectedFutureDate &&
      pickerResult.dateDesiredTime.startsWith(expectedFutureDate) &&
      pickerResult.isSameDayAfterFutureDate === false &&
      pickerResult.hourDesiredTime === `${expectedFutureDate} 12:00` &&
      pickerResult.minuteDesiredTime === `${expectedFutureDate} 12:30`,
    pickerResult,
    `群内登记页时间选择器联动异常：${JSON.stringify(pickerResult)}`
  );

  // 日期/小时/分钟是 picker 控件，必须给出下拉指示；只读的期望时间不能和它们长成同一个样子。
  const pickerFaces = await page.$$(".time-grid .time-picker");
  const pickerChevrons = await page.$$(".time-grid .time-picker__chevron");
  const chevronSizes = [];
  for (const chevron of pickerChevrons) {
    chevronSizes.push(await measure(chevron));
  }
  const previewFace = await page.$(".time-preview");
  const previewBackground = previewFace ? await previewFace.style("background-color") : "";
  const affordanceResult = {
    pickerFaces: pickerFaces.length,
    chevrons: chevronSizes,
    previewBackground,
  };
  addCheck(
    report,
    "registration_picker_affordance",
    pickerFaces.length === 3 &&
      chevronSizes.length === 3 &&
      chevronSizes.every((item) => item && item.width >= 3 && item.height >= 3) &&
      (!previewBackground ||
        previewBackground === "rgba(0, 0, 0, 0)" ||
        previewBackground === "transparent"),
    affordanceResult,
    `群内登记页时间选择器缺少可见下拉指示或预览仍带底色：${JSON.stringify(affordanceResult)}`
  );

  const inputs = await page.$$("input");
  if (inputs.length < 4) {
    throw new Error(`群内登记页输入框数量异常：${inputs.length}`);
  }
  const [nameInput, phoneInput, productInput, quantityInput] = inputs;

  // 校验链属于已登录路径：注入登录态后再按顺序触发必填与格式校验。
  await page.setData({
    canSubmitRegistration: true,
    loginStateText: "登记将关联当前微信身份，门店客服会按此身份跟进",
    loginActionText: "查看身份",
    sessionView: {
      userId: "devtools-registration-user",
      openid: "devtools-registration-openid",
      statusText: "微信身份",
      badgeText: "已登录",
      hintText: "当前身份可用于查询订单和会员资产",
      actionText: "刷新信息",
      loggedIn: true
    }
  });
  await waitForData(page, (data) => data.canSubmitRegistration === true, "登录态注入");

  // input() 先写渲染层，必须等页面数据回写后再点击，否则会按旧值校验。
  const fillField = async (element, field, value, label) => {
    await element.input(value);
    await waitForData(
      page,
      (data) => {
        const current = data[field] === null || data[field] === undefined ? "" : data[field];
        return String(current) === value;
      },
      label
    );
  };

  const validationSteps = [];
  const waitForFeedback = async (expectedText, budgetMs) => {
    const deadline = Date.now() + budgetMs;
    let last = await readSubmitFeedback(page);
    while (Date.now() < deadline) {
      if (last.errorVisible && last.errorMessage.includes(expectedText)) {
        return last;
      }
      await sleep(120);
      last = await readSubmitFeedback(page);
    }
    return last;
  };
  const expectError = async (name, expectedText) => {
    const before = await page.data();
    if (before.submitting) {
      throw new Error(`群内登记校验「${name}」前仍有提交请求在执行`);
    }
    // 自动化输入后立刻点击容易被渲染回写吞掉，先让事件队列稳定下来。
    await sleep(260);
    const attempts = [];
    let feedback = null;
    // 输入后的首次点击可能被输入法或渲染回写吞掉，允许一次重试并记录在报告里。
    for (let attempt = 1; attempt <= 2; attempt += 1) {
      await tapSubmit(page);
      feedback = await waitForFeedback(expectedText, 700);
      const matched = feedback.errorVisible && feedback.errorMessage.includes(expectedText);
      attempts.push({ attempt, matched, ...feedback });
      if (matched) {
        break;
      }
    }
    const matched = feedback.errorVisible && feedback.errorMessage.includes(expectedText);
    validationSteps.push({ name, expectedText, attempts, matched, ...feedback });
    if (!matched) {
      report.errors.push(
        `群内登记校验「${name}」未展示预期提示：实际「${feedback.errorMessage || "空"}」`
      );
    }
  };

  await expectError("empty_name", "请填写联系人");
  await fillField(nameInput, "customerName", "流程审计", "联系人");
  await expectError("invalid_phone", "请填写正确的 11 位手机号");
  await fillField(phoneInput, "customerPhone", "1880000000", "10 位手机号");
  await expectError("short_phone", "请填写正确的 11 位手机号");
  await fillField(phoneInput, "customerPhone", "18800000001", "11 位手机号");
  await fillField(productInput, "productName", "", "清空链接预填商品");
  await expectError("empty_product", "请填写想登记的商品");
  await fillField(productInput, "productName", QUERY_PRODUCT_NAME, "登记商品");
  await fillField(quantityInput, "quantityText", "0", "数量 0");
  await expectError("invalid_quantity", "请填写正确的数量");
  await fillField(quantityInput, "quantityText", "2", "数量 2");

  const tabs = await page.$$(".fulfillment-tab");
  if (tabs.length !== 2) {
    throw new Error(`群内登记页履约方式切换数量异常：${tabs.length}`);
  }
  // 输入框事件后首次点击会被渲染回写吞掉，履约切换失败必须重试而不是直接把审计判为失败。
  const tabTapAttempts = [];
  let deliveryStateFromTap = null;
  for (let attempt = 1; attempt <= 3 && !deliveryStateFromTap; attempt += 1) {
    await sleep(220);
    await tabs[1].tap();
    for (let index = 0; index < 12 && !deliveryStateFromTap; index += 1) {
      await sleep(140);
      const current = await page.data();
      if (current.fulfillmentMethod === "delivery") {
        deliveryStateFromTap = current;
      }
    }
    tabTapAttempts.push({ attempt, switched: Boolean(deliveryStateFromTap) });
  }
  if (!deliveryStateFromTap) {
    throw new Error(`切换到北京闪送失败：${JSON.stringify(tabTapAttempts)}`);
  }
  const deliveryTabText = (await tabs[1].text()).trim();
  const deliveryFeeHint = await page.$(".delivery-fee-hint");
  const deliveryFeeHintText = deliveryFeeHint ? (await deliveryFeeHint.text()).trim() : "";
  addCheck(
    report,
    "registration_delivery_copy",
    deliveryTabText === "北京闪送" &&
      deliveryFeeHintText.includes("运费按收货地址实测") &&
      deliveryFeeHintText.includes("由顾客承担"),
    { tabText: deliveryTabText, feeHint: deliveryFeeHintText, tabTapAttempts },
    "群内登记页闪送口径不一致：应展示“北京闪送”并说明运费按地址实测、由顾客承担"
  );
  const deliveryState = deliveryStateFromTap;
  const deliveryInputs = await page.$$("input");
  await expectError("delivery_without_address", "北京闪送需要填写配送地址");
  const addressInput = deliveryInputs[deliveryInputs.length - 1];
  await fillField(addressInput, "address", "北京市东城区审计路 1 号", "配送地址");
  await captureScreenshot(miniProgram, report, "reports/devtools/final-registration-validation.png");

  const missingCampaignId = `devtools-registration-missing-${Date.now()}`;
  await page.setData({ campaignId: missingCampaignId });
  await tapSubmit(page);
  // 缺失活动批次要等真实后端往返，本地 2s 轮询预算不足，按网络请求预算取证。
  const backendFeedback = await waitForFeedback("活动批次", 8000);
  addCheck(
    report,
    "registration_validation_chain",
    validationSteps.every(
      (step) => step.errorVisible && step.errorMessage.includes(step.expectedText)
    ),
    { steps: validationSteps, deliveryState: deliveryState.fulfillmentMethod },
    "群内登记页必填校验未按顺序拦截缺失或非法输入"
  );
  addCheck(
    report,
    "registration_backend_error",
    backendFeedback.errorVisible &&
      !backendFeedback.submitted &&
      backendFeedback.errorMessage.includes("活动批次"),
    { campaignId: missingCampaignId, feedback: backendFeedback },
    "活动批次不存在时登记页未把后端错误落到页面内提示"
  );

  // 成功态截图前必须清掉上一轮后端错误 Toast，否则会把临时浮层误判成成功态文案冲突。
  await miniProgram.callWxMethod("hideToast");
  await sleep(350);

  await page.setData({
    campaignId: "devtools-registration-audit",
    errorMessage: "",
    submitted: true,
    submitting: false,
    submittedRegistration: {
      id: "gr_devtools_registration_audit",
      campaignId: "devtools-registration-audit",
      groupId: "devtools-group",
      userId: "devtools-user",
      customerName: "流程审计",
      customerPhone: "18800000001",
      productName: QUERY_PRODUCT_NAME,
      quantity: 2,
      fulfillmentMethod: "delivery",
      desiredTime: `${expectedFutureDate} 12:30`,
      address: "北京市东城区审计路 1 号",
      remark: "",
      status: "pending",
      createdAt: "2026-09-13 10:00",
      updatedAt: "2026-09-13 10:00",
    },
  });
  await waitForData(page, (data) => data.submitted === true, "登记成功态渲染");
  const successScrollView = await page.$(".page-scroll");
  const successContentHeight = Number(await successScrollView.scrollHeight());
  await successScrollView.scrollTo(0, successContentHeight);
  await sleep(240);
  const successPanel = await page.$(".success-panel");
  const successActions = await page.$$(".success-actions button");
  const successTitle = await page.$(".success-title");
  const successSubtitle = await page.$(".success-subtitle");
  const successRows = await page.$$(".success-row");
  const successSessionNotice = await page.$("session-notice");
  const successTitleText = successTitle ? (await successTitle.text()).trim() : "";
  const successSubtitleText = successSubtitle ? (await successSubtitle.text()).trim() : "";
  const successSessionText = successSessionNotice ? (await successSessionNotice.text()).trim() : "";
  const successActionSizes = [];
  for (const action of successActions) {
    successActionSizes.push(await measure(action));
  }
  const successPanelBox = await measure(successPanel);
  addCheck(
    report,
    "registration_success_view",
    Boolean(successPanel) &&
      successSessionText.includes("已登录") &&
      successTitleText === "登记已提交" &&
      successSubtitleText.includes("客服") &&
      successRows.length === 4 &&
      successActionSizes.length === 2 &&
      successActionSizes.every((item) => item.height >= MIN_TOUCH_TARGET) &&
      successPanelBox &&
      successPanelBox.bottom <= safeAreaBottom,
    {
      successPanel: successPanelBox,
      successSessionText,
      successTitle: successTitleText,
      successSubtitle: successSubtitleText,
      successRowCount: successRows.length,
      successActionSizes,
      contentHeight: successContentHeight,
    },
    "群内登记提交成功后的回顾信息或后续动作不可完整点击"
  );
  await captureScreenshot(miniProgram, report, "reports/devtools/final-registration-success.png");
}

async function runPolicyAudit(miniProgram, report, shopSettings, windowInfo) {
  const variantResults = [];
  for (const variant of POLICY_VARIANTS) {
    const page = await waitForRoute(miniProgram, POLICY_ROUTE, `?type=${variant.type}`);
    if (page.path !== POLICY_ROUTE) {
      throw new Error(`政策页路由错误：${page.path}`);
    }
    await waitForData(page, (data) => data.loading === false, `${variant.type} 政策内容加载`);
    const data = await page.data();
    const navTitle = await page.$(".page-fixed-safe__title");
    const content = await page.$(".policy-content");
    const contentText = content ? (await content.text()).trim() : "";
    const expectedTitle = shopSettings ? shopSettings[variant.titleKey] : "";
    const expectedContent = shopSettings ? shopSettings[variant.contentKey] : "";
    const scrollView = await page.$(".page-scroll");
    const contentHeight = scrollView ? Number(await scrollView.scrollHeight()) : 0;
    if (scrollView) {
      await scrollView.scrollTo(0, contentHeight);
      await sleep(200);
    }
    const card = await measure(await page.$(".policy-card"));
    const navBack = await measure(await page.$(".page-nav-back"));
    variantResults.push({
      type: variant.type,
      policyTitle: data.policyTitle,
      navTitle: navTitle ? (await navTitle.text()).trim() : "",
      loading: data.loading,
      contentLength: contentText.length,
      contentMatchesConfig: Boolean(expectedContent) && contentText === expectedContent.trim(),
      titleMatchesConfig: Boolean(expectedTitle) && data.policyTitle === expectedTitle.trim(),
      hasPlaceholder: /undefined|null|加载中/.test(contentText),
      contentHeight,
      viewportHeight: windowInfo.windowHeight,
      card,
      navBack,
      screenshot: variant.screenshot,
    });
    await captureScreenshot(miniProgram, report, variant.screenshot);
  }

  const distinctContents = new Set(variantResults.map((item) => item.contentLength));
  const failures = variantResults.filter(
    (item) =>
      item.loading !== false ||
      item.contentLength < 40 ||
      item.hasPlaceholder ||
      !item.contentMatchesConfig ||
      !item.titleMatchesConfig ||
      !item.navTitle ||
      item.navTitle !== item.policyTitle ||
      !item.card ||
      item.card.bottom > windowInfo.safeAreaBottom ||
      !item.navBack ||
      item.navBack.height < MIN_TOUCH_TARGET ||
      item.navBack.width < MIN_TOUCH_TARGET
  );
  addCheck(
    report,
    "policy_variants",
    failures.length === 0 && distinctContents.size === POLICY_VARIANTS.length,
    { variants: variantResults, distinctContentLengths: distinctContents.size },
    `政策页三个变体存在未按运营配置渲染、内容缺失或返回控件过小：${JSON.stringify(
      failures.map((item) => item.type)
    )}`
  );

  const defaultPage = await waitForRoute(miniProgram, POLICY_ROUTE);
  await waitForData(defaultPage, (data) => data.loading === false, "默认政策类型加载");
  const defaultData = await defaultPage.data();
  const expectedDefault = shopSettings ? shopSettings.privacyPolicyTitle : "";
  addCheck(
    report,
    "policy_default_route",
    Boolean(defaultData.policyTitle) &&
      (!expectedDefault || defaultData.policyTitle === expectedDefault.trim()),
    { policyTitle: defaultData.policyTitle, expectedDefault },
    `政策页默认类型未回落到隐私政策：${defaultData.policyTitle || "空"}`
  );
}

async function main() {
  const report = {
    generatedAt: new Date().toISOString(),
    mode: "readonly-and-state-injected",
    wsEndpoint: WS_ENDPOINT,
    apiBaseUrl: API_BASE_URL,
    status: "FAIL",
    checks: [],
    screenshots: [],
    errors: [],
  };
  let miniProgram;

  try {
    miniProgram = await automator.connect({ wsEndpoint: WS_ENDPOINT });
    const windowInfo = await readWindowInfo(miniProgram);
    report.windowInfo = windowInfo;
    const shopSettings = await fetchShopSettings(report);
    report.shopSettingsLoaded = Boolean(shopSettings);

    await runRegistrationAudit(miniProgram, report, windowInfo);
    await runPolicyAudit(miniProgram, report, shopSettings, windowInfo);

    await miniProgram.reLaunch(`/${HOME_ROUTE}`);
    await sleep(400);
    report.status = report.errors.length === 0 ? "PASS" : "FAIL";
  } catch (error) {
    report.errors.push(error instanceof Error ? error.message : String(error));
    report.status = "FAIL";
  } finally {
    if (miniProgram) {
      await miniProgram.disconnect();
    }
    fs.mkdirSync("reports/devtools", { recursive: true });
    report.status = finalizeAuditStatus(report);
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf8");
  }

  console.log(`Registration and policy audit: ${report.status}`);
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
