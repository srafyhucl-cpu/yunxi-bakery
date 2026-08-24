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
  deliveryTypeText: string;
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

function buildOrderDetail(order: OrderSummary): OrderDetailView {
  const items = order.items ?? [];
  const paymentStatus = order.paymentStatus || PAYABLE_PAYMENT_STATUS;
  const statusIndex = ORDER_PROGRESS_STEPS.findIndex((step) => step.status === order.status);
  const isCancelled = order.status === "cancelled";
  const timelineByStatus = new Map((order.timeline ?? []).map((event) => [event.status, event]));
  return {
    ...order,
    statusText: ORDER_STATUS_LABELS[order.status] ?? order.status,
    progressText: isCancelled
      ? "订单已取消，如需继续购买可重新下单或联系客服。"
      : "门店会按订单状态更新制作与配送进度。",
    paymentStatusText: PAYMENT_STATUS_LABELS[paymentStatus] ?? paymentStatus,
    paymentMethodText:
      order.paymentMethod === "mock" ? "MVP 模拟支付" : order.paymentMethod === "wechat" ? "微信支付" : "未记录",
    totalText: formatFen(order.totalFen),
    deliveryTypeText: order.deliveryType === "delivery" ? "门店配送" : "到店自提",
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
    loginStateText: "订单详情需要真实登录后查看",
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
    if (!targetOrderId) {
      wx.showToast({ title: "订单号缺失", icon: "none" });
      return;
    }
    const session = getMiniappSession();
    if (!isMiniappLoggedIn(session)) {
      this.setData({
        order: null,
        canLoadOrder: false,
        sessionView: buildMiniappSessionView(session),
        loginStateText: "请先登录后查看订单详情"
      });
      return;
    }
    this.setData({
      canLoadOrder: true,
      sessionView: buildMiniappSessionView(session),
      loginStateText: "已使用真实登录态加载订单详情"
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
        confirmColor: "#3f7a42",
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
  goChat() {
    if (this.data.loading || this.data.paying || this.data.cancelling) {
      return;
    }
    wx.switchTab({ url: ROUTES.chat });
  },
});
