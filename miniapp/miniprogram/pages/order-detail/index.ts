import {
  ORDER_STATUS_LABELS,
  ORDER_PROGRESS_STEPS,
  PAYABLE_PAYMENT_STATUS,
  PAYMENT_STATUS_LABELS,
  canPayOrder,
  canUserCancelOrder,
} from "../../constants/order";
import { ROUTES } from "../../constants/routes";
import {
  cancelOrder,
  getOrder,
  type OrderSummary,
} from "../../services/orders";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { formatFen } from "../../utils/money";
import { goBackOrHome } from "../../utils/navigation";
import {
  buildOrderAmountView,
  formatPaymentMethodText,
  isBeijingDelivery,
} from "../../utils/order-summary";
import { payOrderById } from "../../utils/order-payment";
import { getMiniappSession } from "../../services/auth";
import { buildMiniappSessionView, isMiniappLoggedIn } from "../../utils/session";

interface OrderItemView {
  productId: string;
  title: string;
  quantity: number;
  priceText: string;
  subtotalText: string;
}

interface OrderDetailView extends OrderSummary {
  statusText: string;
  progressText: string;
  paymentStatusText: string;
  paymentMethodText: string;
  totalText: string;
  goodsTotalText: string;
  deliveryFeeText: string;
  deliveryTypeText: string;
  hasDeliveryFee: boolean;
  receiverLabel: string;
  expectTimeLabel: string;
  canCancel: boolean;
  canPay: boolean;
  itemsView: OrderItemView[];
  progressSteps: Array<{
    status: string;
    title: string;
    description: string;
    timeText: string;
    note: string;
    state: "done" | "current" | "todo" | "cancelled";
  }>;
}

function buildProgressText(order: OrderSummary, beijingDelivery: boolean): string {
  if (order.status === "cancelled") {
    return "订单已取消，如需继续购买可重新下单或联系客服。";
  }
  if (order.status === "done") {
    return "订单已完成，感谢购买。";
  }
  if (order.status === "confirmed") {
    return beijingDelivery
      ? "门店已确认，将按预约时间制作并安排闪送。"
      : "门店已确认，将按预约时间准备取货。";
  }
  if (beijingDelivery) {
    if (order.status === "delivering") {
      return "闪送人员正在配送，请保持收货电话畅通。";
    }
    if (order.status === "making") {
      return "门店正在制作，完成后会交接闪送配送。";
    }
    return "门店确认后会按预约时间制作，请留意闪送进度。";
  }
  if (order.status === "delivering") {
    return "商品已备好，请按预约时间到店取货。";
  }
  if (order.status === "making") {
    return "门店正在制作，完成后会进入待取货状态。";
  }
  return "门店确认后会按预约时间准备商品，请留意取货状态。";
}

function buildOrderDetail(order: OrderSummary): OrderDetailView {
  const items = order.items ?? [];
  const paymentStatus = order.paymentStatus || PAYABLE_PAYMENT_STATUS;
  const statusIndex = ORDER_PROGRESS_STEPS.findIndex((step) => step.status === order.status);
  const isCancelled = order.status === "cancelled";
  const timelineByStatus = new Map((order.timeline ?? []).map((event) => [event.status, event]));
  const amountView = buildOrderAmountView(order);
  const beijingDelivery = isBeijingDelivery(order);
  return {
    ...order,
    statusText: ORDER_STATUS_LABELS[order.status] ?? order.status,
    progressText: buildProgressText(order, beijingDelivery),
    paymentStatusText: PAYMENT_STATUS_LABELS[paymentStatus] ?? paymentStatus,
    paymentMethodText: formatPaymentMethodText(order.paymentMethod),
    totalText: amountView.totalText,
    goodsTotalText: amountView.goodsTotalText,
    deliveryFeeText: amountView.deliveryFeeText,
    deliveryTypeText: amountView.deliveryTypeText,
    hasDeliveryFee: amountView.hasDeliveryFee,
    receiverLabel: beijingDelivery ? "收货人" : "联系人",
    expectTimeLabel: beijingDelivery ? "期望配送" : "预约取货",
    canCancel: canUserCancelOrder(order),
    canPay: canPayOrder(order),
    itemsView: items.map((item) => ({
      productId: item.product_id,
      title: item.title || item.product_id,
      quantity: item.quantity,
      priceText: formatFen(item.price_fen),
      subtotalText: formatFen(item.price_fen * item.quantity),
    })),
    progressSteps: ORDER_PROGRESS_STEPS.map((step, index) => ({
      ...step,
      title:
        step.status === "delivering" ? (beijingDelivery ? "配送中" : "待取货") : step.title,
      description:
        step.status === "delivering"
          ? beijingDelivery
            ? "闪送人员正在送往收货地址"
            : "商品已备好，请按预约时间到店取货"
          : step.description,
      timeText: timelineByStatus.get(step.status)?.createdAt || "",
      note: timelineByStatus.get(step.status)?.note || "",
      state: isCancelled
        ? "cancelled"
        : index < statusIndex
          ? "done"
          : index === statusIndex
            ? "current"
            : "todo",
    })),
  };
}

Page({
  data: {
    orderId: "",
    order: null as OrderDetailView | null,
    loading: false,
    cancelling: false,
    paying: false,
    sessionView: buildMiniappSessionView(getMiniappSession()),
    loginStateText: "登录后可查看金额明细与履约进度",
    canLoadOrder: false,
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onLoad(query: Record<string, string | undefined>) {
    const orderId = query.id || "";
    this.setData({ orderId });
    void this.loadOrder(orderId);
  },
  async loadOrder(orderId?: string) {
    const targetOrderId = orderId || this.data.orderId;
    const session = getMiniappSession();
    if (!isMiniappLoggedIn(session)) {
      this.setData({
        order: null,
        canLoadOrder: false,
        sessionView: buildMiniappSessionView(session),
        loginStateText: "登录后可查看金额明细与履约进度"
      });
      return;
    }
    if (!targetOrderId) {
      this.setData({
        order: null,
        canLoadOrder: true,
        sessionView: buildMiniappSessionView(session),
        loginStateText: "已登录，当前未指定订单"
      });
      wx.showToast({ title: "订单号缺失", icon: "none" });
      return;
    }
    this.setData({
      canLoadOrder: true,
      sessionView: buildMiniappSessionView(session),
      loginStateText: "订单详情已关联当前微信身份"
    });
    this.setData({ loading: true });
    try {
      const order = await getOrder(targetOrderId);
      this.setData({ order: buildOrderDetail(order) });
    } catch {
      wx.showToast({ title: "订单详情加载失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },
  goBack() {
    if (this.data.loading || this.data.paying || this.data.cancelling) {
      return;
    }
    goBackOrHome();
  },
  refreshOrder() {
    if (this.data.loading || this.data.paying || this.data.cancelling) {
      return;
    }
    void this.loadOrder();
  },
  async cancelOrder() {
    const order = this.data.order;
    if (!order || !order.canCancel || this.data.cancelling || this.data.paying || this.data.loading) {
      return;
    }
    const result = await new Promise<boolean>((resolve) => {
      wx.showModal({
        title: "取消订单",
        content: "确认取消这笔订单吗？取消后会释放已预留的商品库存。",
        confirmText: "取消订单",
        confirmColor: "#3D332D",
        success: (modalResult) => resolve(modalResult.confirm),
        fail: () => resolve(false),
      });
    });
    if (!result) {
      return;
    }
    this.setData({ cancelling: true });
    try {
      const cancelledOrder = await cancelOrder(order.id);
      this.setData({ order: buildOrderDetail(cancelledOrder) });
      wx.showToast({ title: "订单已取消", icon: "success" });
    } catch {
      wx.showToast({ title: "取消失败，请联系客服", icon: "none" });
    } finally {
      this.setData({ cancelling: false });
    }
  },
  async payOrder() {
    const order = this.data.order;
    if (!order || !order.canPay || this.data.paying || this.data.cancelling || this.data.loading) {
      return;
    }
    this.setData({ paying: true });
    try {
      const paidOrder = await payOrderById(order.id, () => getOrder(order.id));
      this.setData({ order: buildOrderDetail(paidOrder) });
      wx.showToast({ title: "支付已确认", icon: "success" });
    } catch {
      wx.showToast({ title: "支付失败或已取消", icon: "none" });
    } finally {
      this.setData({ paying: false });
    }
  },
  goOrders() {
    if (this.data.loading || this.data.paying || this.data.cancelling) {
      return;
    }
    wx.reLaunch({ url: ROUTES.orders });
  },
  goProfile() {
    wx.switchTab({ url: ROUTES.profile });
  },
  goChat() {
    if (this.data.loading || this.data.paying || this.data.cancelling) {
      return;
    }
    wx.switchTab({ url: ROUTES.chat });
  },
});
