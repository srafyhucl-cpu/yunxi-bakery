import { ROUTES } from "../../constants/routes";
import { getErrorMessage } from "../../services/http";
import {
  GroupRegistration,
  GroupRegistrationFulfillmentMethod,
  submitGroupRegistration,
} from "../../services/group-registrations";
import { ADDRESS_PHONE_PATTERN } from "../../utils/address-book";
import {
  buildCheckoutHourOptions,
  buildExpectTime,
  CHECKOUT_MINUTE_OPTIONS,
  getDefaultCheckoutHourIndex,
  getCheckoutDateEnd,
  getCheckoutDateStart,
  isCheckoutDateToday,
  resolveCheckoutSchedule,
} from "../../utils/checkout-time";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { goBackOrHome } from "../../utils/navigation";
import { getMiniappSession } from "../../services/auth";
import { buildMiniappSessionView, isMiniappLoggedIn } from "../../utils/session";

function normalizeText(value: string): string {
  return value.trim();
}

function decodeQueryText(value: string | undefined): string {
  if (!value) {
    return "";
  }
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function buildQuantity(value: string): number {
  const quantity = Number.parseInt(value, 10);
  if (Number.isNaN(quantity)) {
    return 0;
  }
  return quantity;
}

const REGISTRATION_BUSINESS_HOURS = "09:00-19:30";

// 可选日期与时段必须按页面打开时的北京时间重建：模块级 data 只在进程启动时求值一次，
// 跨过 17:00 截单点或零点后沿用旧快照会把过期日期与错误的当天标记带进登记。
function buildRegistrationSchedule(expectTime?: string, now = new Date()) {
  const schedule = resolveCheckoutSchedule(
    REGISTRATION_BUSINESS_HOURS,
    expectTime || "",
    CHECKOUT_MINUTE_OPTIONS,
    now
  );
  return {
    dateStartValue: getCheckoutDateStart(now),
    dateEndValue: getCheckoutDateEnd(now),
    selectedDateValue: schedule.dateValue,
    hourOptions: schedule.hourOptions,
    selectedHourIndex: schedule.hourIndex,
    selectedMinuteIndex: schedule.minuteIndex,
    desiredTime: schedule.expectTime,
    isSameDayRegistration: isCheckoutDateToday(schedule.dateValue, now)
  };
}

Page({
  data: {
    campaignId: "",
    groupName: "",
    campaignTitle: "群内福利登记",
    customerName: "",
    customerPhone: "",
    productName: "",
    quantityText: "1",
    fulfillmentMethod: "pickup" as GroupRegistrationFulfillmentMethod,
    ...buildRegistrationSchedule(),
    minuteOptions: CHECKOUT_MINUTE_OPTIONS,
    address: "",
    remark: "",
    errorMessage: "",
    submitting: false,
    submitted: false,
    submittedRegistration: null as GroupRegistration | null,
    sessionView: buildMiniappSessionView(getMiniappSession()),
    canSubmitRegistration: false,
    loginStateText: "登录后登记记录会归属到当前微信身份，便于门店客服跟进",
    loginActionText: "去登录",
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onLoad(query: Record<string, string | undefined>) {
    const productName = decodeQueryText(query.productName);
    const session = getMiniappSession();
    const loggedIn = isMiniappLoggedIn(session);
    this.setData({
      ...buildRegistrationSchedule(),
      campaignId: normalizeText(decodeQueryText(query.campaignId)),
      groupName: decodeQueryText(query.groupName),
      campaignTitle: decodeQueryText(query.title) || "群内福利登记",
      productName,
      sessionView: buildMiniappSessionView(session),
      canSubmitRegistration: loggedIn,
      loginStateText: loggedIn
        ? "登记将关联当前微信身份，门店客服会按此身份跟进"
        : "请先登录后提交群内登记，避免登记记录无法归属到你",
      loginActionText: loggedIn ? "查看身份" : "去登录"
    });
  },
  onShow() {
    // 页面在后台跨过截单点或零点后重新展示时，重建基线并把过期选择抬到最早可预约时间。
    this.setData(buildRegistrationSchedule(this.data.desiredTime));
  },
  goBack() {
    if (this.data.submitting) {
      return;
    }
    goBackOrHome();
  },
  goHome() {
    if (this.data.submitting) {
      return;
    }
    wx.switchTab({ url: ROUTES.home });
  },
  goChat() {
    if (this.data.submitting) {
      return;
    }
    wx.switchTab({ url: ROUTES.chat });
  },
  goProfile() {
    if (this.data.submitting) {
      return;
    }
    wx.switchTab({ url: ROUTES.profile });
  },
  updateField(event: WechatMiniprogram.Input) {
    const field = event.currentTarget.dataset.field as string;
    this.setData({
      [field]: event.detail.value,
      errorMessage: ""
    });
  },
  selectFulfillmentMethod(event: WechatMiniprogram.TouchEvent) {
    const fulfillmentMethod = event.currentTarget.dataset.method as GroupRegistrationFulfillmentMethod;
    this.setData({
      fulfillmentMethod,
      address: fulfillmentMethod === "pickup" ? "" : this.data.address,
      errorMessage: ""
    });
  },
  selectDesiredDate(event: WechatMiniprogram.PickerChange) {
    const selectedDateValue = String(event.detail.value);
    const hourOptions = buildCheckoutHourOptions(REGISTRATION_BUSINESS_HOURS, selectedDateValue);
    const selectedHourIndex = getDefaultCheckoutHourIndex(hourOptions);
    this.setData({
      selectedDateValue,
      hourOptions,
      selectedHourIndex,
      desiredTime: buildExpectTime(
        selectedDateValue,
        hourOptions[selectedHourIndex] || "18",
        this.data.minuteOptions[this.data.selectedMinuteIndex] || "00"
      ),
      isSameDayRegistration: isCheckoutDateToday(selectedDateValue),
      errorMessage: ""
    });
  },
  selectDesiredHour(event: WechatMiniprogram.PickerChange) {
    const selectedHourIndex = Number(event.detail.value);
    const hourValue = this.data.hourOptions[selectedHourIndex] || this.data.hourOptions[0] || "18";
    this.setData({
      selectedHourIndex,
      desiredTime: buildExpectTime(
        this.data.selectedDateValue,
        hourValue,
        this.data.minuteOptions[this.data.selectedMinuteIndex] || "00"
      ),
      errorMessage: ""
    });
  },
  selectDesiredMinute(event: WechatMiniprogram.PickerChange) {
    const selectedMinuteIndex = Number(event.detail.value);
    const minuteValue =
      this.data.minuteOptions[selectedMinuteIndex] || this.data.minuteOptions[0] || "00";
    const hourValue =
      this.data.hourOptions[this.data.selectedHourIndex] || this.data.hourOptions[0] || "18";
    this.setData({
      selectedMinuteIndex,
      desiredTime: buildExpectTime(this.data.selectedDateValue, hourValue, minuteValue),
      errorMessage: ""
    });
  },
  showValidationError(message: string) {
    this.setData({ errorMessage: message });
    wx.showToast({ title: message, icon: "none" });
  },
  validateForm(): boolean {
    const campaignId = normalizeText(this.data.campaignId);
    const customerName = normalizeText(this.data.customerName);
    const customerPhone = normalizeText(this.data.customerPhone);
    const productName = normalizeText(this.data.productName);
    const quantity = buildQuantity(this.data.quantityText);
    const desiredTime = normalizeText(this.data.desiredTime);
    const address = normalizeText(this.data.address);
    const remark = normalizeText(this.data.remark);
    if (!campaignId) {
      this.showValidationError("登记链接缺少活动信息，请联系群内客服");
      return false;
    }
    if (!customerName) {
      this.showValidationError("请填写联系人");
      return false;
    }
    if (!ADDRESS_PHONE_PATTERN.test(customerPhone)) {
      this.showValidationError("请填写正确的 11 位手机号");
      return false;
    }
    if (!productName) {
      this.showValidationError("请填写想登记的商品");
      return false;
    }
    if (quantity <= 0) {
      this.showValidationError("请填写正确的数量");
      return false;
    }
    if (!desiredTime) {
      this.showValidationError("请选择期望取货/配送时间");
      return false;
    }
    if (this.data.fulfillmentMethod === "delivery" && !address) {
      this.showValidationError("北京闪送需要填写配送地址");
      return false;
    }
    this.setData({
      campaignId,
      customerName,
      customerPhone,
      productName,
      quantityText: String(quantity),
      desiredTime,
      address,
      remark,
      errorMessage: ""
    });
    return true;
  },
  async submitRegistration() {
    if (this.data.submitting || this.data.submitted) {
      return;
    }
    if (!this.data.canSubmitRegistration) {
      this.showValidationError("请先登录后提交群内登记");
      return;
    }
    if (!this.validateForm()) {
      return;
    }
    this.setData({ submitting: true, errorMessage: "" });
    try {
      const registration = await submitGroupRegistration({
        campaignId: this.data.campaignId,
        customerName: this.data.customerName,
        customerPhone: this.data.customerPhone,
        productName: this.data.productName,
        quantity: buildQuantity(this.data.quantityText),
        fulfillmentMethod: this.data.fulfillmentMethod,
        desiredTime: this.data.desiredTime,
        address: this.data.fulfillmentMethod === "delivery" ? this.data.address : "",
        remark: this.data.remark
      });
      this.setData({
        submitted: true,
        submittedRegistration: registration
      });
      wx.showToast({ title: "登记已提交", icon: "success" });
    } catch (error) {
      const message = getErrorMessage(error, "登记失败，请稍后重试");
      this.setData({ errorMessage: message });
      wx.showToast({ title: message, icon: "none" });
    } finally {
      this.setData({ submitting: false });
    }
  }
});
