import { cancelOrder, getOrder, listOrders, type OrderSummary } from "../../services/orders";
import {
  DEFAULT_ORDER_LIST_FILTER,
  ORDER_LIST_FILTERS,
  ORDER_STATUS_LABELS,
  PAYMENT_STATUS_LABELS,
  canPayOrder,
  canUserCancelOrder,
  type OrderListFilterKey,
} from "../../constants/order";
import { ROUTES } from "../../constants/routes";
import { getMiniappSession } from "../../services/auth";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { formatFen } from "../../utils/money";
import { goBackOrHome } from "../../utils/navigation";
import { payOrderById } from "../../utils/order-payment";
import { buildMiniappSessionView, isMiniappLoggedIn } from "../../utils/session";

interface OrderView extends OrderSummary {
  statusText: string;
  paymentStatusText: string;
  totalText: string;
  canPay: boolean;
  canCancel: boolean;
}

interface OrderFilterTabView {
  key: OrderListFilterKey;
  label: string;
  count: number;
  selected: boolean;
}

function statusText(status: string): string {
  return ORDER_STATUS_LABELS[status] ?? status;
}

function paymentStatusText(status?: string): string {
  return PAYMENT_STATUS_LABELS[status || "unpaid"] ?? (status || "待支付");
}

function buildOrderView(order: OrderSummary): OrderView {
  return {
    ...order,
    statusText: statusText(order.status),
    paymentStatusText: paymentStatusText(order.paymentStatus),
    totalText: formatFen(order.totalFen),
    canPay: canPayOrder(order),
    canCancel: canUserCancelOrder(order),
  };
}

function getOrderFilter(key: OrderListFilterKey) {
  return ORDER_LIST_FILTERS.find((filter) => filter.key === key) || ORDER_LIST_FILTERS[0];
}

function buildFilterTabs(orders: OrderView[], activeFilter: OrderListFilterKey): OrderFilterTabView[] {
  return ORDER_LIST_FILTERS.map((filter) => ({
    key: filter.key,
    label: filter.label,
    count: orders.filter(filter.match).length,
    selected: filter.key === activeFilter,
  }));
}

function filterOrders(orders: OrderView[], activeFilter: OrderListFilterKey): OrderView[] {
  return orders.filter(getOrderFilter(activeFilter).match);
}

function getEmptyText(activeFilter: OrderListFilterKey): string {
  return getOrderFilter(activeFilter).emptyText;
}

function replaceOrder(orders: OrderView[], updatedOrder: OrderSummary): OrderView[] {
  return orders.map((order) => (order.id === updatedOrder.id ? buildOrderView(updatedOrder) : order));
}

Page({
  data: {
    allOrders: [] as OrderView[],
    filteredOrders: [] as OrderView[],
    filterTabs: buildFilterTabs([], DEFAULT_ORDER_LIST_FILTER),
    activeFilter: DEFAULT_ORDER_LIST_FILTER as OrderListFilterKey,
    emptyText: getEmptyText(DEFAULT_ORDER_LIST_FILTER),
    sessionView: buildMiniappSessionView(getMiniappSession()),
    loginStateText: "订单需要真实登录后查看",
    canUseOrders: false,
    loading: false,
    payingOrderId: "",
    cancellingOrderId: "",
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onShow() {
    void this.loadOrders();
  },
  goBack() {
    if (this.data.payingOrderId || this.data.cancellingOrderId) {
      return;
    }
    goBackOrHome();
  },
  async loadOrders() {
    const session = getMiniappSession();
    if (!isMiniappLoggedIn(session)) {
      this.setData({
        allOrders: [] as OrderView[],
        filteredOrders: [] as OrderView[],
        filterTabs: buildFilterTabs([], DEFAULT_ORDER_LIST_FILTER),
        activeFilter: DEFAULT_ORDER_LIST_FILTER as OrderListFilterKey,
        emptyText: "请先登录后查看订单",
        sessionView: buildMiniappSessionView(session),
        loginStateText: "请先登录后查看订单",
        canUseOrders: false,
        loading: false
      });
      return;
    }
    this.setData({ loading: true });
    try {
      const allOrders = (await listOrders()).map(buildOrderView);
      this.setData({
        sessionView: buildMiniappSessionView(session),
        loginStateText: "已使用真实登录态加载订单",
        canUseOrders: true
      });
      this.applyOrderFilter(allOrders, this.data.activeFilter);
    } catch {
      wx.showToast({ title: "订单加载失败", icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },
  applyOrderFilter(allOrders: OrderView[], activeFilter: OrderListFilterKey) {
    this.setData({
      allOrders,
      activeFilter,
      filterTabs: buildFilterTabs(allOrders, activeFilter),
      filteredOrders: filterOrders(allOrders, activeFilter),
      emptyText: getEmptyText(activeFilter),
    });
  },
  selectFilter(event: WechatMiniprogram.TouchEvent) {
    const filterKey = event.currentTarget.dataset.key as OrderListFilterKey | undefined;
    if (!filterKey || filterKey === this.data.activeFilter) {
      return;
    }
    this.applyOrderFilter(this.data.allOrders, filterKey);
  },
  openOrder(event: WechatMiniprogram.TouchEvent) {
    if (!this.data.canUseOrders) {
      wx.showToast({ title: "请先登录后查看订单", icon: "none" });
      return;
    }
    const orderId = event.currentTarget.dataset.id as string;
    if (!orderId) {
      return;
    }
    wx.navigateTo({ url: `${ROUTES.orderDetail}?id=${orderId}` });
  },
  async payOrder(event: WechatMiniprogram.TouchEvent) {
    if (!this.data.canUseOrders) {
      wx.showToast({ title: "请先登录后支付", icon: "none" });
      return;
    }
    const orderId = event.currentTarget.dataset.id as string;
    const order = this.data.allOrders.find((item) => item.id === orderId);
    if (!order || !order.canPay || this.data.payingOrderId || this.data.cancellingOrderId) {
      return;
    }
    this.setData({ payingOrderId: orderId });
    try {
      const paidOrder = await payOrderById(orderId, () => getOrder(orderId));
      this.applyOrderFilter(replaceOrder(this.data.allOrders, paidOrder), this.data.activeFilter);
      wx.showToast({ title: "支付已确认", icon: "success" });
    } catch {
      wx.showToast({ title: "支付失败或已取消", icon: "none" });
    } finally {
      this.setData({ payingOrderId: "" });
    }
  },
  async cancelOrder(event: WechatMiniprogram.TouchEvent) {
    if (!this.data.canUseOrders) {
      wx.showToast({ title: "请先登录后取消订单", icon: "none" });
      return;
    }
    const orderId = event.currentTarget.dataset.id as string;
    const order = this.data.allOrders.find((item) => item.id === orderId);
    if (!order || !order.canCancel || this.data.payingOrderId || this.data.cancellingOrderId) {
      return;
    }
    const confirmed = await new Promise<boolean>((resolve) => {
      wx.showModal({
        title: "取消订单",
        content: "确认取消这笔订单吗？取消后会释放已预留的商品库存。",
        confirmText: "取消订单",
        confirmColor: "#3f7a42",
        success: (modalResult) => resolve(modalResult.confirm),
        fail: () => resolve(false),
      });
    });
    if (!confirmed) {
      return;
    }
    this.setData({ cancellingOrderId: orderId });
    try {
      const cancelledOrder = await cancelOrder(orderId);
      this.applyOrderFilter(replaceOrder(this.data.allOrders, cancelledOrder), this.data.activeFilter);
      wx.showToast({ title: "订单已取消", icon: "success" });
    } catch {
      wx.showToast({ title: "取消失败，请联系客服", icon: "none" });
    } finally {
      this.setData({ cancellingOrderId: "" });
    }
  },
});
