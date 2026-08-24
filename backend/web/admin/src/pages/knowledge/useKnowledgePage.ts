import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import { knowledgeService } from "@/services/knowledge";
import type { KnowledgeDraft, KnowledgeEntry } from "@/types/knowledge";

const DEFAULT_PAGE = 1;

const emptyDraft = (): KnowledgeDraft => ({
  title: "",
  content: "",
  contentType: "faq",
  keywords: "",
  priority: 50,
  isActive: true,
  audience: "all",
  reviewStatus: "published",
  validFrom: "",
  validUntil: "",
});

function parsePage(rawValue: unknown): number {
  const parsed = Number(rawValue);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : DEFAULT_PAGE;
}

function normalizeText(rawValue: unknown): string {
  return typeof rawValue === "string" ? rawValue.trim() : "";
}

function formatTime(value: string): string {
  return value ? value.replace("T", " ").slice(0, 19) : "未记录";
}

export function useKnowledgePage() {
  const route = useRoute();
  const router = useRouter();

  const loading = ref(false);
  const saving = ref(false);
  const actionId = ref<number | null>(null);
  const drawerVisible = ref(false);
  const drawerMode = ref<"create" | "edit">("create");
  const errorMessage = ref("");
  const entries = ref<KnowledgeEntry[]>([]);
  const selectedEntry = ref<KnowledgeEntry | null>(null);
  const history = ref<Array<Record<string, unknown>>>([]);
  const total = ref(0);
  const totalActive = ref(0);
  const totalFailed = ref(0);
  const pageSize = ref(30);

  const filterDraft = reactive({
    contentType: normalizeText(route.query.contentType),
    isActive: normalizeText(route.query.isActive),
    vectorStatus: normalizeText(route.query.vectorStatus),
    keyword: normalizeText(route.query.keyword),
  });
  const form = reactive<KnowledgeDraft>(emptyDraft());

  const currentPage = computed(() => parsePage(route.query.page));
  const queryContentType = computed(() => normalizeText(route.query.contentType));
  const queryIsActive = computed(() => normalizeText(route.query.isActive));
  const queryVectorStatus = computed(() => normalizeText(route.query.vectorStatus));
  const queryKeyword = computed(() => normalizeText(route.query.keyword));

  const activeCount = computed(() => entries.value.filter((item) => item.isActive).length);
  const failedSyncCount = computed(() =>
    entries.value.filter((item) => item.vectorSyncStatus === "failed").length,
  );

  const rows = computed(() =>
    entries.value.map((item) => ({
      ...item,
      activeLabel: item.isActive ? "启用" : "停用",
      typeLabel: formatContentType(item.contentType),
      audienceLabel: formatAudience(item.audience),
      reviewLabel: formatReviewStatus(item.reviewStatus),
      reviewType: formatReviewType(item.reviewStatus),
      syncLabel: formatSyncStatus(item.vectorSyncStatus),
      syncType: formatSyncType(item.vectorSyncStatus),
      updatedAtLabel: formatTime(item.updatedAt),
      validityLabel: formatValidity(item.validFrom, item.validUntil),
    })),
  );

  async function loadEntries() {
    loading.value = true;
    errorMessage.value = "";
    try {
      const payload = await knowledgeService.listEntries({
        page: currentPage.value,
        contentType: queryContentType.value,
        isActive: queryIsActive.value,
        vectorStatus: queryVectorStatus.value,
        keyword: queryKeyword.value,
      });
      entries.value = payload.items;
      total.value = payload.total;
      totalActive.value = payload.totalActive;
      totalFailed.value = payload.totalFailed;
      pageSize.value = payload.pageSize;
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : "知识配置加载失败，请稍后重试";
    } finally {
      loading.value = false;
    }
  }

  async function submitFilters() {
    await router.replace({ query: buildQuery(DEFAULT_PAGE) });
  }

  async function changePage(page: number) {
    await router.replace({ query: buildQuery(page) });
  }

  function openCreate() {
    drawerMode.value = "create";
    selectedEntry.value = null;
    history.value = [];
    Object.assign(form, emptyDraft());
    drawerVisible.value = true;
  }

  async function openEdit(entry: KnowledgeEntry) {
    drawerMode.value = "edit";
    selectedEntry.value = entry;
    Object.assign(form, toDraft(entry));
    drawerVisible.value = true;
    try {
      const detail = await knowledgeService.getEntry(entry.id);
      selectedEntry.value = detail.entry;
      history.value = detail.history;
      Object.assign(form, toDraft(detail.entry));
    } catch {
      history.value = [];
    }
  }

  function closeDrawer() {
    drawerVisible.value = false;
  }

  async function saveEntry() {
    if (!form.title.trim() || !form.content.trim()) {
      ElMessage.warning("请先填写标题和内容");
      return;
    }
    saving.value = true;
    try {
      if (drawerMode.value === "create") {
        await knowledgeService.createEntry({ ...form });
        ElMessage.success("知识条目已创建");
      } else if (selectedEntry.value) {
        await knowledgeService.updateEntry(selectedEntry.value.id, { ...form });
        ElMessage.success("知识条目已保存");
      }
      drawerVisible.value = false;
      await loadEntries();
    } finally {
      saving.value = false;
    }
  }

  async function toggleEntry(entry: KnowledgeEntry) {
    actionId.value = entry.id;
    try {
      const updated = await knowledgeService.toggleActive(entry.id);
      ElMessage.success(`${updated.title} 已${updated.isActive ? "启用" : "停用"}`);
      await loadEntries();
    } finally {
      actionId.value = 0;
    }
  }

  async function retrySync(entry: KnowledgeEntry) {
    actionId.value = entry.id;
    try {
      await knowledgeService.retrySync(entry.id);
      ElMessage.success("已重新触发向量同步");
      await loadEntries();
    } finally {
      actionId.value = 0;
    }
  }

  async function suggestCategory() {
    if (!form.title.trim() && !form.content.trim()) {
      ElMessage.warning("请先输入标题或内容");
      return;
    }
    const suggestion = await knowledgeService.suggestCategory(form.title, form.content);
    form.contentType = suggestion.content_type;
    ElMessage.success(`建议分类：${suggestion.label}`);
  }

  function buildQuery(page: number): Record<string, string> {
    const query: Record<string, string> = {};
    if (page > 1) {
      query.page = String(page);
    }
    if (filterDraft.contentType) {
      query.contentType = filterDraft.contentType;
    }
    if (filterDraft.isActive) {
      query.isActive = filterDraft.isActive;
    }
    if (filterDraft.vectorStatus) {
      query.vectorStatus = filterDraft.vectorStatus;
    }
    if (filterDraft.keyword.trim()) {
      query.keyword = filterDraft.keyword.trim();
    }
    return query;
  }

  watch(
    () => route.query,
    async () => {
      filterDraft.contentType = queryContentType.value;
      filterDraft.isActive = queryIsActive.value;
      filterDraft.vectorStatus = queryVectorStatus.value;
      filterDraft.keyword = queryKeyword.value;
      await loadEntries();
    },
    { immediate: true },
  );

  async function resetFilters() {
    filterDraft.contentType = "";
    filterDraft.isActive = "";
    filterDraft.vectorStatus = "";
    filterDraft.keyword = "";
    await router.replace({ query: {} });
  }

  return {
    loading,
    saving,
    actionId,
    drawerVisible,
    drawerMode,
    errorMessage,
    rows,
    selectedEntry,
    history,
    total,
    pageSize,
    activeCount,
    failedSyncCount,
    currentPage,
    filterDraft,
    form,
    loadEntries,
    submitFilters,
    resetFilters,
    changePage,
    openCreate,
    openEdit,
    closeDrawer,
    saveEntry,
    toggleEntry,
    retrySync,
    suggestCategory,
  };
}

function toDraft(entry: KnowledgeEntry): KnowledgeDraft {
  return {
    title: entry.title,
    content: entry.content,
    contentType: entry.contentType || "faq",
    keywords: entry.keywords,
    priority: entry.priority,
    isActive: entry.isActive,
    audience: entry.audience || "all",
    reviewStatus: entry.reviewStatus || "published",
    validFrom: entry.validFrom || "",
    validUntil: entry.validUntil || "",
  };
}

function formatContentType(value: string): string {
  const map: Record<string, string> = {
    faq: "FAQ",
    rule: "规则",
    copywriting: "话术",
    product: "商品知识",
  };
  return map[value] || value || "未分类";
}

function formatSyncStatus(value: string): string {
  const map: Record<string, string> = {
    success: "已入向量",
    failed: "同步失败",
    syncing: "同步中",
    pending: "待同步",
  };
  return map[value] || "未记录";
}

function formatSyncType(value: string): "success" | "warning" | "danger" | "info" {
  if (value === "success") {
    return "success";
  }
  if (value === "failed") {
    return "danger";
  }
  if (value === "syncing" || value === "pending") {
    return "warning";
  }
  return "info";
}

function formatAudience(value: string): string {
  const map: Record<string, string> = {
    all: "共同",
    customer: "客户",
    employee: "员工",
  };
  return map[value] || "共同";
}

function formatReviewStatus(value: string): string {
  const map: Record<string, string> = {
    draft: "草稿",
    published: "已发布",
    archived: "已归档",
  };
  return map[value] || "已发布";
}

function formatReviewType(value: string): "success" | "warning" | "danger" | "info" {
  if (value === "published") {
    return "success";
  }
  if (value === "archived") {
    return "info";
  }
  return "warning";
}

function formatValidity(validFrom: string, validUntil: string): string {
  if (validFrom && validUntil) {
    return `${validFrom} 至 ${validUntil}`;
  }
  if (validFrom) {
    return `${validFrom} 起`;
  }
  if (validUntil) {
    return `至 ${validUntil}`;
  }
  return "长期有效";
}
