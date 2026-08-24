import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { observabilityService } from "@/services/observability";
import type {
  ObservabilityDetailField,
  ObservabilityHistoryItem,
  ObservabilitySummary,
  ObservabilityTab,
  ObservabilityWebhookItem,
} from "@/types/observability";

type WorkbenchMode = "workspace" | "failures";

const DEFAULT_PAGE = 1;
const PAGE_SIZE = 30;

function parsePage(rawValue: unknown): number {
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return DEFAULT_PAGE;
  }
  return Math.floor(parsed);
}

function normalizeText(rawValue: unknown): string {
  return typeof rawValue === "string" ? rawValue.trim() : "";
}

function normalizeTab(rawValue: unknown, mode: WorkbenchMode): ObservabilityTab {
  const allowed: ObservabilityTab[] =
    ["history", "webhooks"];
  const value = normalizeText(rawValue) as ObservabilityTab;
  return allowed.includes(value) ? value : allowed[0];
}

function formatTime(value: string): string {
  return value ? value.replace("T", " ").slice(0, 19) : "未记录";
}

function formatStatusType(value: string): "success" | "warning" | "danger" | "info" {
  if (value === "success") {
    return "success";
  }
  if (value === "failed" || value === "error") {
    return "danger";
  }
  if (value === "processing" || value === "syncing") {
    return "warning";
  }
  return "info";
}

function formatStatusText(value: string): string {
  if (value === "success") {
    return "成功";
  }
  if (value === "failed" || value === "error") {
    return "失败";
  }
  if (value === "processing" || value === "syncing") {
    return "处理中";
  }
  return value || "未标记";
}

export function useObservabilityWorkbench(mode: WorkbenchMode) {
  const route = useRoute();
  const router = useRouter();

  const loading = ref(false);
  const detailLoading = ref(false);
  const drawerVisible = ref(false);
  const errorMessage = ref("");
  const summaryErrorMessage = ref("");
  const summary = ref<ObservabilitySummary | null>(null);
  const total = ref(0);
  const historyItems = ref<ObservabilityHistoryItem[]>([]);
  const webhookItems = ref<ObservabilityWebhookItem[]>([]);

  const historySourceDraft = ref("");
  const historyStatusDraft = ref(mode === "failures" ? "failed" : "");
  const historyEntityTypeDraft = ref("");
  const historyKeywordDraft = ref("");

  const webhookStatusDraft = ref(mode === "failures" ? "failed" : "");
  const webhookEventTypeDraft = ref("");
  const webhookKeywordDraft = ref("");

  const detailTitle = ref("");
  const detailSubtitle = ref("");
  const detailSummaryLines = ref<string[]>([]);
  const detailFields = ref<ObservabilityDetailField[]>([]);
  const detailErrorMessage = ref("");

  const activeTab = computed(() => normalizeTab(route.query.tab, mode));
  const currentPage = computed(() => parsePage(route.query.page));

  const queryHistorySource = computed(() => normalizeText(route.query.historySource));
  const queryHistoryStatus = computed(() =>
    normalizeText(route.query.historyStatus) || (mode === "failures" ? "failed" : ""),
  );
  const queryHistoryEntityType = computed(() => normalizeText(route.query.historyEntityType));
  const queryHistoryKeyword = computed(() => normalizeText(route.query.historyKeyword));

  const queryWebhookStatus = computed(() =>
    normalizeText(route.query.webhookStatus) || (mode === "failures" ? "failed" : ""),
  );
  const queryWebhookEventType = computed(() => normalizeText(route.query.webhookEventType));
  const queryWebhookKeyword = computed(() => normalizeText(route.query.webhookKeyword));

  const listCount = computed(() => {
    if (activeTab.value === "history") {
      return historyItems.value.length;
    }
    return webhookItems.value.length;
  });

  const issueCount = computed(() => {
    if (activeTab.value === "history") {
      return historyItems.value.filter((item) => item.status === "failed").length;
    }
    return webhookItems.value.filter((item) => item.status === "failed").length;
  });

  const summaryLabel = computed(() => {
    if (activeTab.value === "history") {
      return "回写记录总数";
    }
    return "Webhook 记录总数";
  });

  const summaryStatusType = computed<"success" | "warning" | "danger">(() => {
    if (summaryErrorMessage.value) {
      return "danger";
    }
    return summary.value?.status === "attention" ? "warning" : "success";
  });

  const summaryStatusLabel = computed(() => {
    if (summaryErrorMessage.value) {
      return "摘要加载失败";
    }
    return summary.value?.status === "attention" ? "需要值守" : "运行平稳";
  });

  const summaryCards = computed(() => {
    const counts = summary.value?.counts;
    return [
      {
        label: "回写失败",
        value: counts?.contentChangeFailures ?? 0,
        route: "/observability/failures?tab=history",
        level: counts?.contentChangeFailures ? "danger" : "normal",
      },
      {
        label: "Webhook 失败",
        value: counts?.webhookFailures ?? 0,
        route: "/observability/failures?tab=webhooks",
        level: counts?.webhookFailures ? "danger" : "normal",
      },
      {
        label: "慢 Webhook",
        value: counts?.slowWebhooks ?? 0,
        route: "/observability/sessions?tab=webhooks",
        level: counts?.slowWebhooks ? "warning" : "normal",
      },
      {
        label: "处理中",
        value: counts?.webhookProcessing ?? 0,
        route: "/observability/sessions?tab=webhooks&webhookStatus=processing",
        level: counts?.webhookProcessing ? "info" : "normal",
      },
    ];
  });

  const historyRows = computed(() =>
    historyItems.value.map((item) => ({
      ...item,
      occurredAtLabel: formatTime(item.occurredAt),
      statusType: formatStatusType(item.status),
      statusLabel: formatStatusText(item.status),
      errorLabel: item.errorMessage || item.errorType || "-",
    })),
  );

  const webhookRows = computed(() =>
    webhookItems.value.map((item) => ({
      ...item,
      receivedAtLabel: formatTime(item.receivedAt),
      statusType: formatStatusType(item.status),
      statusLabel: formatStatusText(item.status),
      durationLabel: item.durationMs > 0 ? `${item.durationMs} ms` : "-",
      errorLabel: item.errorMessage || item.errorType || "-",
    })),
  );

  async function loadData() {
    loading.value = true;
    errorMessage.value = "";
    try {

      if (activeTab.value === "history") {
        const payload = await observabilityService.listHistory({
          page: currentPage.value,
          source: queryHistorySource.value,
          status: queryHistoryStatus.value,
          entityType: queryHistoryEntityType.value,
          keyword: queryHistoryKeyword.value,
        });
        historyItems.value = payload.items;
        total.value = payload.total;
        return;
      }

      const payload = await observabilityService.listWebhooks({
        page: currentPage.value,
        status: queryWebhookStatus.value,
        eventType: queryWebhookEventType.value,
        keyword: queryWebhookKeyword.value,
      });
      webhookItems.value = payload.items;
      total.value = payload.total;
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "数据加载失败，请稍后重试";
    } finally {
      loading.value = false;
    }
  }

  async function loadSummary() {
    summaryErrorMessage.value = "";
    try {
      summary.value = await observabilityService.getSummary();
    } catch (error) {
      summary.value = null;
      summaryErrorMessage.value = error instanceof Error ? error.message : "值守摘要加载失败";
    }
  }

  async function retryLoadData() {
    await loadData();
  }

  async function switchTab(tab: ObservabilityTab) {
    await router.replace({ query: buildQuery(tab, DEFAULT_PAGE) });
  }

  async function changePage(page: number) {
    await router.replace({ query: buildQuery(activeTab.value, page) });
  }

  async function submitHistoryFilters() {
    await router.replace({ query: buildQuery("history", DEFAULT_PAGE) });
  }

  async function submitWebhookFilters() {
    await router.replace({ query: buildQuery("webhooks", DEFAULT_PAGE) });
  }

  const detailEntityKey = ref("");
  const detailEntityType = ref("");

  function closeDrawer() {
    drawerVisible.value = false;
    detailLoading.value = false;
    detailTitle.value = "";
    detailSubtitle.value = "";
    detailSummaryLines.value = [];
    detailFields.value = [];
    detailErrorMessage.value = "";
    detailEntityKey.value = "";
    detailEntityType.value = "";
  }

  async function trackEntityHistory(entityKey: string, entityType: string) {
    closeDrawer();
    historyEntityTypeDraft.value = entityType?.toLowerCase() === "product" ? "product" : (entityType?.toLowerCase() === "knowledge" ? "knowledge" : "");
    historyKeywordDraft.value = entityKey;
    historySourceDraft.value = "";
    historyStatusDraft.value = mode === "failures" ? "failed" : "";
    await router.replace({ query: buildQuery("history", DEFAULT_PAGE) });
  }

  async function openHistoryDetail(item: ObservabilityHistoryItem) {
    drawerVisible.value = true;
    detailLoading.value = true;
    detailTitle.value = item.title;
    detailSubtitle.value = `${item.entityType} · ${item.entityKey}`;
    detailErrorMessage.value = "";
    try {
      const detail = await observabilityService.getHistoryDetail(item.id);
      detailTitle.value = detail.title;
      detailSubtitle.value = `${detail.entityType} · ${detail.entityKey}`;
      detailSummaryLines.value = detail.summaryLines;
      detailFields.value = detail.detailFields;
      detailErrorMessage.value = detail.errorMessage;
    } catch (error) {
      detailSummaryLines.value = [];
      detailFields.value = [];
      detailErrorMessage.value = error instanceof Error ? error.message : "详情加载失败，请稍后重试";
    } finally {
      detailLoading.value = false;
    }
  }

  async function openWebhookDetail(item: ObservabilityWebhookItem) {
    drawerVisible.value = true;
    detailLoading.value = true;
    detailTitle.value = item.eventType || item.msgId || "Webhook 详情";
    detailSubtitle.value = `${item.businessType || "event"} · ${item.businessKey || "-"}`;
    detailErrorMessage.value = "";
    try {
      const detail = await observabilityService.getWebhookDetail(item.id);
      detailTitle.value = detail.eventType || detail.msgId || "Webhook 详情";
      detailSubtitle.value = `${detail.businessType || "event"} · ${detail.businessKey || "-"}`;
      detailSummaryLines.value = detail.summaryLines;
      detailFields.value = detail.detailFields;
      detailErrorMessage.value = detail.errorMessage;
    } catch (error) {
      detailSummaryLines.value = [];
      detailFields.value = [];
      detailErrorMessage.value = error instanceof Error ? error.message : "详情加载失败，请稍后重试";
    } finally {
      detailLoading.value = false;
    }
  }

  function buildQuery(tab: ObservabilityTab, page: number): Record<string, string> {
    const query: Record<string, string> = { tab };
    if (page > 1) {
      query.page = String(page);
    }

    if (tab === "history") {
      if (historySourceDraft.value) {
        query.historySource = historySourceDraft.value;
      }
      if (historyStatusDraft.value) {
        query.historyStatus = historyStatusDraft.value;
      }
      if (historyEntityTypeDraft.value) {
        query.historyEntityType = historyEntityTypeDraft.value;
      }
      if (historyKeywordDraft.value) {
        query.historyKeyword = historyKeywordDraft.value.trim();
      }
      return query;
    }

    if (webhookStatusDraft.value) {
      query.webhookStatus = webhookStatusDraft.value;
    }
    if (webhookEventTypeDraft.value) {
      query.webhookEventType = webhookEventTypeDraft.value;
    }
    if (webhookKeywordDraft.value) {
      query.webhookKeyword = webhookKeywordDraft.value.trim();
    }
    return query;
  }

  watch(
    () => route.query,
    async () => {

      historySourceDraft.value = queryHistorySource.value;
      historyStatusDraft.value = queryHistoryStatus.value;
      historyEntityTypeDraft.value = queryHistoryEntityType.value;
      historyKeywordDraft.value = queryHistoryKeyword.value;

      webhookStatusDraft.value = queryWebhookStatus.value;
      webhookEventTypeDraft.value = queryWebhookEventType.value;
      webhookKeywordDraft.value = queryWebhookKeyword.value;

      await Promise.all([loadSummary(), loadData()]);
    },
    { immediate: true },
  );

  return {
    loading,
    detailLoading,
    drawerVisible,
    errorMessage,
    summary,
    summaryCards,
    summaryErrorMessage,
    summaryStatusLabel,
    summaryStatusType,
    total,
    pageSize: PAGE_SIZE,
    activeTab,
    currentPage,
    historyRows,
    webhookRows,
    historySourceDraft,
    historyStatusDraft,
    historyEntityTypeDraft,
    historyKeywordDraft,
    webhookStatusDraft,
    webhookEventTypeDraft,
    webhookKeywordDraft,
    detailTitle,
    detailSubtitle,
    detailSummaryLines,
    detailFields,
    detailErrorMessage,
    detailEntityKey,
    detailEntityType,
    listCount,
    issueCount,
    summaryLabel,
    switchTab,
    changePage,
    submitHistoryFilters,
    submitWebhookFilters,
    closeDrawer,
    openHistoryDetail,
    openWebhookDetail,
    trackEntityHistory,
    retryLoadData,
  };
}
