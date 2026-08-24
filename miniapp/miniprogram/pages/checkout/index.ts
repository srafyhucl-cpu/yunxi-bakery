import { ROUTES } from "../../constants/routes";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { getErrorMessage } from "../../services/http";
import {
  cancelOrder,
  createOrder,
  payWithBalance,
  prepareCombinedPayment,
  prepareOrderPayment
} from "../../services/orders";
import { getProductDetail } from "../../services/products";
import { getShopSettings } from "../../services/shop-settings";
import { getMiniappSession } from "../../services/auth";
import {
  ADDRESS_PHONE_PATTERN,
  getSelectedAddress,
  syncAddressBookFromBackend,
} from "../../utils/address-book";
import { clearCartItems, getCartItems } from "../../utils/cart";
import {
  buildDefaultExpectTime,
  buildCheckoutHourOptions,
  buildExpectTime,
  CHECKOUT_MINUTE_OPTIONS,
  getDefaultCheckoutHourIndex,
  getCheckoutDateEnd,
  getCheckoutDateStart,
} from "../../utils/checkout-time";
import { formatFen } from "../../utils/money";
import { goBackOrHome } from "../../utils/navigation";
import { buildMiniappSessionView, isMiniappLoggedIn } from "../../utils/session";
import { getBalance } from "../../services/balance";
import { applyCoupon, getMyCoupons } from "../../services/coupons";
import { applyPoints, getPoints } from "../../services/points";
import { ONLINE_PAYMENT_READY } from "../../services/payment-gate";
import { executePreparedPayment } from "../../utils/order-payment";
import {
  buildPaymentBranch,
  classifyCouponStatus,
  type MemberCoupon,
  type PaymentBranch
} from "../../utils/member-assets";

function normalizeText(value: string): string {
  return value.trim();
}

function getOrderDeliveryAddress(deliveryType: "pickup" | "delivery", deliveryAddress: string): string {
  return deliveryType === "delivery" ? deliveryAddress : "";
}

function buildOrderRemark(
  deliveryType: "pickup" | "delivery",
  remark: string,
  pickupNote: string
): string {
  if (deliveryType !== "pickup" || !pickupNote) {
    return remark;
  }
  return [remark, `自提说明：${pickupNote}`].filter(Boolean).join("；");
}

function getCartItemLabel(item: CartItem): string {
  return item.title || item.productId;
}

Page({
  data: {
    receiverName: "",
    receiverPhone: "",
    deliveryType: "pickup" as "pickup" | "delivery",
    deliveryAddress: "",
    expectTime: "",
    remark: "",
    pickupNotice: "",
    deliveryNotice: "",
    pickupAddress: "",
    selectedAddressId: "",
    selectedAddressText: "",
    dateStartValue: getCheckoutDateStart(),
    dateEndValue: getCheckoutDateEnd(),
    selectedDateValue: buildDefaultExpectTime().slice(0, 10),
    hourOptions: buildCheckoutHourOptions("09:00-20:00"),
    minuteOptions: CHECKOUT_MINUTE_OPTIONS,
    selectedHourIndex: getDefaultCheckoutHourIndex(buildCheckoutHourOptions("09:00-20:00")),
    selectedMinuteIndex: 0,
    totalText: "¥0.00",
    errorMessage: "",
    submitting: false,
    agreementAccepted: false,
    sessionView: buildMiniappSessionView(getMiniappSession()),
    loginStateText: "结算需要真实登录后使用",
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle,
    availableCoupons: [] as Array<MemberCoupon & { disabled: boolean }>,
    selectedCouponId: "",
    pointsEnabled: false,
    pointsBalance: 0,
    balanceEnabled: true,
    balanceFen: 0,
    goodsFen: 0,
    estimateCouponFen: 0,
    estimateRemainFen: 0,
    goodsFenText: "¥0.00",
    estimateCouponFenText: "-¥0.00",
    estimateRemainFenText: "¥0.00",
    balanceDeductText: "-¥0.00",
    pendingOrderId: "",
    pendingBarVisible: false,
    showCouponPanel: false,
    orderLocked: false
  },
  onShow() {
    void this.loadCheckout();
  },
  goBack() {
    if (this.data.submitting) {
      return;
    }
    goBackOrHome();
  },
  async loadCheckout() {
    const session = getMiniappSession();
    if (!isMiniappLoggedIn(session)) {
      this.setData({
        errorMessage: "请先登录后再结算",
        sessionView: buildMiniappSessionView(session),
        loginStateText: "请先登录后再结算"
      });
      return;
    }
    this.setData({
      sessionView: buildMiniappSessionView(session),
      loginStateText: "已使用真实登录态加载结算信息"
    });
    const totalFen = getCartItems().reduce((sum, item) => sum + item.priceFen * item.quantity, 0);
    const shopSettings = await getShopSettings();
    await syncAddressBookFromBackend();
    const selectedAddress = getSelectedAddress();
    const hourOptions = buildCheckoutHourOptions(shopSettings.businessHours);
    const defaultHourIndex = getDefaultCheckoutHourIndex(hourOptions);
    const defaultExpectTime = buildDefaultExpectTime(shopSettings.businessHours);
    const shouldApplySelectedAddress =
      Boolean(selectedAddress) &&
      (this.data.selectedAddressId !== selectedAddress?.id ||
        (!this.data.receiverName && !this.data.receiverPhone && !this.data.deliveryAddress));
    this.setData({
      totalText: formatFen(totalFen),
      pickupNotice: shopSettings.pickupNotice,
      deliveryNotice: shopSettings.deliveryNotice,
      pickupAddress: shopSettings.pickupAddress,
      selectedAddressId: selectedAddress?.id || "",
      receiverName: shouldApplySelectedAddress
        ? selectedAddress?.receiverName || ""
        : this.data.receiverName,
      receiverPhone: shouldApplySelectedAddress
        ? selectedAddress?.receiverPhone || ""
        : this.data.receiverPhone,
      deliveryAddress: shouldApplySelectedAddress
        ? this.data.deliveryType === "delivery"
          ? selectedAddress?.address || ""
          : ""
        : this.data.deliveryAddress,
      selectedAddressText: selectedAddress
        ? `${selectedAddress.receiverName} ${selectedAddress.receiverPhone}`
        : "选择常用地址",
      dateStartValue: getCheckoutDateStart(),
      dateEndValue: getCheckoutDateEnd(),
      hourOptions,
      selectedHourIndex: defaultHourIndex,
      expectTime: this.data.expectTime || defaultExpectTime,
      selectedDateValue: (this.data.expectTime || defaultExpectTime).slice(0, 10)
    });
    // 资产区数据（余额/积分/可用券）用于展示与抵扣估算
    const [balance, points, couponsData] = await Promise.all([
      getBalance().catch(() => null),
      getPoints().catch(() => null),
      getMyCoupons().catch(() => null)
    ]);
    const goodsFen = getCartItems().reduce((sum, item) => sum + item.priceFen * item.quantity, 0);
    const availableCoupons = couponsData
      ? this.buildCouponList(couponsData.coupons || [], goodsFen)
      : [];
    const pending = this.readPendingOrder();
    const pendingBarVisible =
      pending !== null &&
      pending.signature === getCartItems().map((item) => `${item.productId}:${item.quantity}`).join(",");
    this.setData({
      goodsFen,
      balanceFen: balance ? balance.balanceFen : 0,
      pointsBalance: points ? points.pointsBalance : 0,
      availableCoupons,
      pendingOrderId: pending ? pending.orderId : "",
      pendingBarVisible,
      selectedCouponId: pending ? pending.couponId : "",
      pointsEnabled: pending ? pending.pointsEnabled : false
    });
    this.refreshEstimate();
  },
  updateField(event: WechatMiniprogram.Input) {
    const field = event.currentTarget.dataset.field as string;
    this.setData({
      [field]: event.detail.value
    });
  },
  openAddressBook() {
    wx.navigateTo({ url: `${ROUTES.address}?mode=select` });
  },
  selectDeliveryType(event: WechatMiniprogram.TouchEvent) {
    const deliveryType = event.currentTarget.dataset.type as "pickup" | "delivery";
    const selectedAddress = getSelectedAddress();
    this.setData({
      deliveryType,
      deliveryAddress: deliveryType === "delivery" ? selectedAddress?.address || this.data.deliveryAddress : "",
      errorMessage: ""
    });
  },
  selectExpectDate(event: WechatMiniprogram.PickerChange) {
    const selectedDateValue = String(event.detail.value);
    this.setData({
      selectedDateValue,
      expectTime: buildExpectTime(
        selectedDateValue,
        this.data.hourOptions[this.data.selectedHourIndex] || "18",
        this.data.minuteOptions[this.data.selectedMinuteIndex] || "00"
      ),
      errorMessage: ""
    });
  },
  selectExpectHour(event: WechatMiniprogram.PickerChange) {
    const selectedHourIndex = Number(event.detail.value);
    const hourValue = this.data.hourOptions[selectedHourIndex] || this.data.hourOptions[0] || "18";
    const dateValue = this.data.selectedDateValue;
    this.setData({
      selectedHourIndex,
      expectTime: buildExpectTime(
        dateValue,
        hourValue,
        this.data.minuteOptions[this.data.selectedMinuteIndex] || "00"
      ),
      errorMessage: ""
    });
  },
  selectExpectMinute(event: WechatMiniprogram.PickerChange) {
    const selectedMinuteIndex = Number(event.detail.value);
    const minuteValue =
      this.data.minuteOptions[selectedMinuteIndex] || this.data.minuteOptions[0] || "00";
    const dateValue = this.data.selectedDateValue;
    const hourValue = this.data.hourOptions[this.data.selectedHourIndex] || this.data.hourOptions[0] || "18";
    this.setData({
      selectedMinuteIndex,
      expectTime: buildExpectTime(dateValue, hourValue, minuteValue),
      errorMessage: ""
    });
  },
  showValidationError(message: string) {
    this.setData({ errorMessage: message });
    wx.showToast({ title: message, icon: "none" });
  },
  buildCouponList(coupons: MemberCoupon[], goodsFen: number) {
    return coupons
      .filter((coupon) => classifyCouponStatus(coupon).tab === "available")
      .map((coupon) => ({
        ...coupon,
        disabled: coupon.thresholdFen > 0 && goodsFen < coupon.thresholdFen
      }));
  },
  savePendingOrder(orderId: string) {
    const signature = getCartItems()
      .map((item) => `${item.productId}:${item.quantity}`)
      .join(",");
    wx.setStorageSync("yunxiPendingOrder", {
      orderId,
      signature,
      couponId: this.data.selectedCouponId,
      pointsEnabled: this.data.pointsEnabled
    });
  },
  readPendingOrder(): { orderId: string; signature: string; couponId: string; pointsEnabled: boolean } | null {
    return wx.getStorageSync("yunxiPendingOrder") || null;
  },
  clearPendingOrder() {
    wx.removeStorageSync("yunxiPendingOrder");
  },
  refreshEstimate() {
    const goodsFen = this.data.goodsFen;
    const selected = this.data.availableCoupons.find(
      (coupon) => coupon.couponId === this.data.selectedCouponId
    );
    const couponFen = selected && !selected.disabled ? selected.valueFen : 0;
    const balanceFen = this.data.balanceEnabled ? this.data.balanceFen : 0;
    const remainFen = Math.max(0, goodsFen - couponFen - balanceFen);
    this.setData({
      estimateCouponFen: couponFen,
      estimateRemainFen: remainFen,
      goodsFenText: formatFen(goodsFen),
      estimateCouponFenText: `-${formatFen(couponFen)}`,
      estimateRemainFenText: formatFen(remainFen),
      balanceDeductText: `-${formatFen(Math.min(balanceFen, goodsFen))}`
    });
  },
  toggleCouponPanel() {
    this.setData({ showCouponPanel: !this.data.showCouponPanel });
  },
  selectCoupon(event: WechatMiniprogram.TouchEvent) {
    const couponId = event.currentTarget.dataset.id as string;
    const coupon = this.data.availableCoupons.find((item) => item.couponId === couponId);
    if (coupon && coupon.disabled) {
      return;
    }
    // 订单已生成（快照已写）：已应用券不可退选（后端无撤销端点），允许换选（apply 覆盖写）
    if (this.data.orderLocked && this.data.selectedCouponId === couponId) {
      wx.showToast({ title: "已应用优惠券，如需取消请取消订单", icon: "none" });
      return;
    }
    this.setData({
      selectedCouponId: this.data.selectedCouponId === couponId ? "" : couponId,
      showCouponPanel: false
    });
    this.refreshEstimate();
  },
  onPointsSwitch(event: WechatMiniprogram.SwitchChange) {
    if (this.data.orderLocked) {
      this.setData({ pointsEnabled: true });
      wx.showToast({ title: "积分已应用，如需取消请取消订单", icon: "none" });
      return;
    }
    this.setData({ pointsEnabled: Boolean(event.detail.value) });
    this.refreshEstimate();
  },
  togglePointsRow() {
    if (this.data.orderLocked) {
      wx.showToast({ title: "积分已应用，如需取消请取消订单", icon: "none" });
      return;
    }
    this.setData({ pointsEnabled: !this.data.pointsEnabled });
    this.refreshEstimate();
  },
  onBalanceSwitch(event: WechatMiniprogram.SwitchChange) {
    this.setData({ balanceEnabled: Boolean(event.detail.value) });
    this.refreshEstimate();
  },
  toggleBalanceRow() {
    this.setData({ balanceEnabled: !this.data.balanceEnabled });
    this.refreshEstimate();
  },
  validateOrderForm(): boolean {
    const receiverName = normalizeText(this.data.receiverName);
    const receiverPhone = normalizeText(this.data.receiverPhone);
    const deliveryAddress = normalizeText(this.data.deliveryAddress);
    const expectTime = normalizeText(this.data.expectTime);
    if (!receiverName) {
      this.showValidationError("请填写联系人");
      return false;
    }
    if (!ADDRESS_PHONE_PATTERN.test(receiverPhone)) {
      this.showValidationError("请填写正确的 11 位手机号");
      return false;
    }
    if (this.data.deliveryType === "delivery" && !deliveryAddress) {
      this.showValidationError("门店配送需要填写配送地址");
      return false;
    }
    if (!expectTime) {
      this.showValidationError("请填写期望取货/配送时间");
      return false;
    }
    if (!this.data.agreementAccepted) {
      this.showValidationError("请先阅读并同意用户协议和隐私政策");
      return false;
    }
    this.setData({
      receiverName,
      receiverPhone,
      deliveryAddress,
      expectTime,
      remark: normalizeText(this.data.remark),
      errorMessage: ""
    });
    return true;
  },
  async validateCartProducts(cartItems: CartItem[]): Promise<boolean> {
    try {
      const products = await Promise.all(
        cartItems.map((item) => getProductDetail(item.productId, { forceRefresh: true }))
      );
      const invalidItems: string[] = [];
      const unavailableItems: string[] = [];
      products.forEach((product, index) => {
        const cartItem = cartItems[index];
        if (!cartItem || !product) {
          invalidItems.push(cartItem ? getCartItemLabel(cartItem) : "未知商品");
          return;
        }
        if (!product.isActive || product.stock < cartItem.quantity) {
          unavailableItems.push(getCartItemLabel(cartItem));
        }
      });
      if (invalidItems.length) {
        this.showValidationError(`购物车商品已失效，请重新选择：${invalidItems.join("、")}`);
        return false;
      }
      if (unavailableItems.length) {
        this.showValidationError(`商品库存不足或已下架：${unavailableItems.join("、")}`);
        return false;
      }
      return true;
    } catch {
      this.showValidationError("商品信息校验失败，请稍后重试");
      return false;
    }
  },
  toggleAgreementAccepted() {
    this.setData({
      agreementAccepted: !this.data.agreementAccepted,
      errorMessage: ""
    });
  },
  openPolicy(event: WechatMiniprogram.TouchEvent) {
    const policyType = event.currentTarget.dataset.type as string;
    wx.navigateTo({ url: `${ROUTES.policy}?type=${policyType}` });
  },
  async submitOrder() {
    if (this.data.submitting) {
      return;
    }
    if (!isMiniappLoggedIn(getMiniappSession())) {
      this.showValidationError("请先登录后提交订单");
      return;
    }
    const cartItems = getCartItems();
    if (!cartItems.length) {
      this.showValidationError("购物车为空，请先选择商品");
      return;
    }
    if (!this.validateOrderForm()) {
      return;
    }
    this.setData({ errorMessage: "", submitting: true });
    try {
      const cartStillValid = await this.validateCartProducts(cartItems);
      if (!cartStillValid) {
        return;
      }
      let orderId = this.data.pendingOrderId;
      if (!orderId) {
        const order = await createOrder({
          items: cartItems.map((item) => ({
            productId: item.productId,
            quantity: item.quantity,
            title: item.title,
            priceFen: item.priceFen
          })),
          receiverName: this.data.receiverName,
          receiverPhone: this.data.receiverPhone,
          deliveryType: this.data.deliveryType,
          deliveryAddress: getOrderDeliveryAddress(this.data.deliveryType, this.data.deliveryAddress),
          expectTime: this.data.expectTime,
          remark: buildOrderRemark(this.data.deliveryType, this.data.remark, this.data.deliveryAddress)
        });
        orderId = order.orderId;
        this.savePendingOrder(orderId);
        this.setData({ pendingOrderId: orderId, orderLocked: true });
      }
      // 按序 apply（弹窗确认前不改订单金额展示，只写后端快照）
      let couponFen = 0;
      if (this.data.selectedCouponId) {
        const applied = await applyCoupon(orderId, this.data.selectedCouponId);
        couponFen = applied.couponFen || 0;
      }
      let pointsFen = 0;
      if (this.data.pointsEnabled) {
        const applied = await applyPoints(orderId);
        pointsFen = applied.pointsFen || 0;
      }
      const totalFen = this.data.goodsFen;
      const remainFen = Math.max(0, totalFen - couponFen - pointsFen);
      const balance = await getBalance();
      const branch = buildPaymentBranch({
        remainFen,
        balanceFen: this.data.balanceEnabled ? balance.balanceFen : 0,
        balanceEnabled: this.data.balanceEnabled
      });
      await this.confirmAndPay(orderId, { totalFen, couponFen, pointsFen, remainFen, branch, balanceFen: balance.balanceFen });
    } catch (error) {
      const message = getErrorMessage(error, "提交失败，请稍后重试");
      this.setData({ errorMessage: message });
      wx.showToast({ title: message, icon: "none" });
    } finally {
      this.setData({ submitting: false });
    }
  },
  async confirmAndPay(
    orderId: string,
    summary: {
      totalFen: number;
      couponFen: number;
      pointsFen: number;
      remainFen: number;
      branch: PaymentBranch;
      balanceFen: number;
    }
  ): Promise<void> {
    const { totalFen, couponFen, pointsFen, remainFen, branch, balanceFen } = summary;
    let content = "";
    if (branch === "free") {
      content = "本单已由优惠全额抵扣，无需支付";
    } else if (branch === "balance") {
      content = `实付 ${formatFen(remainFen)}（余额支付）`;
    } else if (branch === "combined") {
      const onlineFen = Math.max(0, remainFen - balanceFen);
      content = `剩余应付 ${formatFen(remainFen)}\n余额抵扣 ${formatFen(balanceFen)}\n在线支付 ${formatFen(onlineFen)}`;
    } else {
      content = `实付 ${formatFen(remainFen)}（在线支付）`;
    }
    if (couponFen > 0) {
      content += `\n优惠券 -${formatFen(couponFen)}`;
    }
    if (pointsFen > 0) {
      content += `\n积分 -${formatFen(pointsFen)}`;
    }
    const confirmed = await new Promise<boolean>((resolve) => {
      wx.showModal({
        title: "确认支付",
        content,
        confirmText: branch === "free" ? "确认完成" : "确认支付",
        cancelText: "稍后支付",
        success: (res) => resolve(Boolean(res.confirm)),
        fail: () => resolve(false)
      });
    });
    if (!confirmed) {
      wx.showToast({ title: "订单已保留，可继续支付或取消订单", icon: "none" });
      return;
    }
    if (branch === "free") {
      await payWithBalance(orderId);
    } else if (branch === "balance") {
      await payWithBalance(orderId);
    } else if (branch === "combined") {
      if (!ONLINE_PAYMENT_READY) {
        wx.showToast({ title: "在线支付即将上线，请到店支付或联系客服", icon: "none" });
        return;
      }
      const payment = await prepareCombinedPayment(orderId, balanceFen);
      await executePreparedPayment(payment);
    } else {
      if (!ONLINE_PAYMENT_READY) {
        wx.showToast({ title: "在线支付即将上线，请到店支付或联系客服", icon: "none" });
        return;
      }
      const payment = await prepareOrderPayment(orderId);
      await executePreparedPayment(payment);
    }
    this.clearPendingOrder();
    clearCartItems();
    wx.showToast({ title: "支付成功", icon: "success" });
    wx.redirectTo({ url: `${ROUTES.orderDetail}?id=${orderId}` });
  },
  async resumePendingOrder() {
    const pending = this.readPendingOrder();
    if (!pending) {
      return;
    }
    this.setData({
      pendingOrderId: pending.orderId,
      selectedCouponId: pending.couponId,
      pointsEnabled: pending.pointsEnabled,
      pendingBarVisible: false,
      orderLocked: true
    });
    wx.showToast({ title: "已恢复待支付订单，积分与已选券已锁定，请确认支付", icon: "none" });
  },
  async cancelPendingOrder() {
    const pending = this.readPendingOrder();
    if (!pending) {
      return;
    }
    try {
      await cancelOrder(pending.orderId);
      this.clearPendingOrder();
      this.setData({ pendingOrderId: "", pendingBarVisible: false, orderLocked: false });
      wx.showToast({ title: "订单已取消", icon: "success" });
    } catch (error) {
      wx.showToast({ title: getErrorMessage(error, "取消失败"), icon: "none" });
    }
  }
});
