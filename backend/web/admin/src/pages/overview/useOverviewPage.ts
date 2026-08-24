import { computed, ref } from "vue";

import { observabilityService } from "@/services/observability";
import { ordersService } from "@/services/orders";
import { productsService } from "@/services/products";
import { settingsService } from "@/services/settings";
import { shopPagesService } from "@/services/shopPages";
import { transfersService } from "@/services/transfers";
import { orderStatusLabel } from "@/constants/orderStatus";
import type { OrderListItem } from "@/types/order";

interface OverviewRecentIssue {
  title: string;
  description: string;
  route: string;
  level: "success" | "warning" | "danger" | "info";
}

const FIRST_PAGE = 1;

export function useOverviewPage() {
  const loading = ref(false);
  const errorMessage = ref("");
  const lastRefreshedAt = ref("");
  const productTotal = ref(0);
  const activeProductTotal = ref(0);
  const inactiveProductTotal = ref(0);
  const orderTotal = ref(0);
  const pendingOrderCount = ref(0);
  const orderAmountText = ref("¥0.00");
  const pendingTransferCount = ref(0);
  const failedHistoryTotal = ref(0);
  const failedWebhookTotal = ref(0);
  const slowWebhookTotal = ref(0);
  const processingWebhookTotal = ref(0);
  const configuredSettingCount = ref(0);
  const decorationStatusText = ref("未发布");
  const decorationUpdatedAt = ref("");
  const recentOrders = ref<Array<OrderListItem & { statusText: string; totalText: string }>>([]);
  const recentIssues = ref<OverviewRecentIssue[]>([]);

  const hasFailures = computed(
    () => failedHistoryTotal.value + failedWebhookTotal.value + slowWebhookTotal.value > 0,
  );

  const healthLabel = computed(() => {
    if (errorMessage.value) return "需要检查";
    if (pendingOrderCount.value > 0 || pendingTransferCount.value > 0 || hasFailures.value) {
      return "有待处理";
    }
    return "运营平稳";
  });

  const healthType = computed<"success" | "warning" | "danger">(() => {
    if (errorMessage.value) return "danger";
    return pendingOrderCount.value > 0 || pendingTransferCount.value > 0 || hasFailures.value
      ? "warning"
      : "success";
  });

  async function loadOverview() {
    loading.value = true;
    errorMessage.value = "";

    const [orders, pendingOrders, products, transfers, observabilitySummary, settings, homePage] =
      await Promise.allSettled([
        ordersService.listOrders(FIRST_PAGE),
        ordersService.listOrders(FIRST_PAGE, "", "pending"),
        productsService.listProducts(FIRST_PAGE, "", "all"),
        transfersService.listPendingTransfers(),
        observabilityService.getSummary(),
        settingsService.getSummary(),
        shopPagesService.getPage("home"),
      ]);

    if (orders.status === "fulfilled") {
      orderTotal.value = orders.value.total;
      orderAmountText.value = formatFen(
        orders.value.items.reduce((sum, item) => sum + item.totalFen, 0),
      );
      recentOrders.value = orders.value.items.slice(0, 5).map((item) => ({
        ...item,
        statusText: orderStatusLabel(item.status),
        totalText: formatFen(item.totalFen),
      }));
    }
    if (pendingOrders.status === "fulfilled") {
      pendingOrderCount.value = pendingOrders.value.total;
    }
    if (products.status === "fulfilled") {
      productTotal.value = products.value.total;
      activeProductTotal.value = products.value.totalActive;
      inactiveProductTotal.value = products.value.totalInactive;
    }
    if (transfers.status === "fulfilled") {
      pendingTransferCount.value = transfers.value.length;
    }
    if (observabilitySummary.status === "fulfilled") {
      failedHistoryTotal.value = observabilitySummary.value.counts.contentChangeFailures;
      failedWebhookTotal.value = observabilitySummary.value.counts.webhookFailures;
      slowWebhookTotal.value = observabilitySummary.value.counts.slowWebhooks;
      processingWebhookTotal.value = observabilitySummary.value.counts.webhookProcessing;
    }
    if (settings.status === "fulfilled") {
      configuredSettingCount.value = [
        settings.value.api.adminTokenConfigured,
        settings.value.channels.youzan.clientIdConfigured,
        settings.value.channels.youzan.clientSecretConfigured,
        settings.value.channels.youzan.kdtIdConfigured,
        settings.value.channels.wecom.corpIdConfigured,
        settings.value.channels.wecom.agentIdConfigured,
        settings.value.channels.wecom.robotWebhookConfigured,
      ].filter(Boolean).length;
    }
    if (homePage.status === "fulfilled") {
      decorationStatusText.value = homePage.value.published?.status === "published" ? "首页已发布" : "未发布";
      decorationUpdatedAt.value = homePage.value.published?.updatedAt || "";
    }

    recentIssues.value = buildRecentIssues();
    const failedRequests = [orders, pendingOrders, products, transfers, observabilitySummary, settings, homePage]
      .filter((item) => item.status === "rejected").length;
    if (failedRequests > 0) {
      errorMessage.value = `${failedRequests} 个概览指标加载失败，请刷新重试`;
    }
    lastRefreshedAt.value = new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    loading.value = false;
  }

  function buildRecentIssues(): OverviewRecentIssue[] {
    const issues: OverviewRecentIssue[] = [];
    if (pendingOrderCount.value > 0) {
      issues.push({
        title: "有待确认订单",
        description: `${pendingOrderCount.value} 个小程序订单等待门店确认`,
        route: "/orders?status=pending",
        level: "warning",
      });
    }
    if (pendingTransferCount.value > 0) {
      issues.push({
        title: "有待处理转人工",
        description: `${pendingTransferCount.value} 个会话正在等待接单或处理`,
        route: "/transfers",
        level: "warning",
      });
    }
    if (failedHistoryTotal.value > 0 || failedWebhookTotal.value > 0 || slowWebhookTotal.value > 0) {
      issues.push({
        title: "数据链路需要排查",
        description: "存在回写失败、Webhook 失败或慢处理事件",
        route: "/observability/failures",
        level: "danger",
      });
    }
    if (!issues.length) {
      issues.push({
        title: "暂无高优先级事项",
        description: "可以继续检查商品、装修和店铺配置",
        route: "/settings/shop",
        level: "success",
      });
    }
    return issues;
  }

  return {
    loading,
    errorMessage,
    lastRefreshedAt,
    productTotal,
    activeProductTotal,
    inactiveProductTotal,
    orderTotal,
    pendingOrderCount,
    orderAmountText,
    pendingTransferCount,
    failedHistoryTotal,
    failedWebhookTotal,
    slowWebhookTotal,
    processingWebhookTotal,
    configuredSettingCount,
    decorationStatusText,
    decorationUpdatedAt,
    recentOrders,
    recentIssues,
    healthLabel,
    healthType,
    loadOverview,
  };
}

function formatFen(value: number): string {
  return `¥${(value / 100).toFixed(2)}`;
}
