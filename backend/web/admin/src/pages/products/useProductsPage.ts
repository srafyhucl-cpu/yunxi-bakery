import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import { productsService, type ReconcileResult } from "@/services/products";
import { featuredProductsService } from "@/services/featuredProducts";
import type { ProductListItem } from "@/types/product";
import { formatSyncSource } from "@/utils/syncSourceLabel";

const DEFAULT_PAGE = 1;

function parsePage(rawValue: unknown): number {
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return DEFAULT_PAGE;
  }
  return Math.floor(parsed);
}

function normalizeKeyword(rawValue: unknown): string {
  return typeof rawValue === "string" ? rawValue.trim() : "";
}

export function useProductsPage() {
  const route = useRoute();
  const router = useRouter();

  const loading = ref(false);
  const togglingId = ref(0);
  const reconciling = ref(false);
  const drawerVisible = ref(false);
  const products = ref<ProductListItem[]>([]);
  const total = ref(0);
  const totalActive = ref(0);
  const totalInactive = ref(0);
  const pageSize = ref(30);
  const selectedProduct = ref<ProductListItem | null>(null);
  const searchDraft = ref(normalizeKeyword(route.query.keyword));
  const filterActive = ref(route.query.is_active !== undefined ? String(route.query.is_active) : "1");
  const filterSyncStatus = ref(String(route.query.vector_sync_status ?? ""));
  const filterFeatured = ref(route.query.featured === "1");
  const filterItemNo = ref(String(route.query.item_no ?? ""));
  const filterStockLevel = ref(String(route.query.stock_level ?? ""));

  const featuredTitles = ref<string[]>([]);
  const togglingFeaturedId = ref(0);

  const currentPage = computed(() => parsePage(route.query.page));
  const currentKeyword = computed(() => normalizeKeyword(route.query.keyword));
  const currentActive = computed(() => {
    const act = route.query.is_active;
    if (act === undefined) return "1";
    if (act === "all") return "";
    return String(act);
  });
  const currentSyncStatus = computed(() => String(route.query.vector_sync_status ?? ""));
  const currentFeatured = computed(() => route.query.featured === "1");
  const currentItemNo = computed(() => String(route.query.item_no ?? ""));
  const currentStockLevel = computed(() => String(route.query.stock_level ?? ""));
  const currentSortBy = computed(() => String(route.query.sort_by ?? ""));
  const currentSortOrder = computed(() => String(route.query.sort_order ?? ""));
  const activeCount = computed(() => products.value.filter((item) => item.isActive).length);

  const tableRows = computed(() =>
    products.value.map((item) => ({
      ...item,
      syncSourceLabel: formatSyncSource(item.lastSyncSource),
      syncStatusLabel: formatSyncStatus(item.vectorSyncStatus),
      activeLabel: item.isActive ? "在售" : "下架",
      isFeatured: featuredTitles.value.includes(item.title),
    })),
  );

  const displayedTableRows = computed(() => {
    const level = filterStockLevel.value;
    if (!level) return tableRows.value;
    return tableRows.value.filter((row) => {
      const s = row.stock;
      if (level === "sufficient") return s != null && s > 200;
      if (level === "low") return s != null && s > 0 && s <= 200;
      if (level === "zero") return s == null || s === 0;
      return true;
    });
  });

  async function loadFeaturedTitles() {
    featuredTitles.value = await featuredProductsService.getFeaturedProducts();
  }

  async function toggleFeatured(product: ProductListItem) {
    togglingFeaturedId.value = product.id;
    try {
      const titles = [...featuredTitles.value];
      const idx = titles.indexOf(product.title);
      if (idx >= 0) {
        titles.splice(idx, 1);
        await featuredProductsService.saveFeaturedProducts(titles);
        ElMessage.success(`已从主推款移除：${product.title}`);
      } else {
        titles.push(product.title);
        await featuredProductsService.saveFeaturedProducts(titles);
        ElMessage.success(`已加入主推款：${product.title}`);
      }
      featuredTitles.value = titles;
    } finally {
      togglingFeaturedId.value = 0;
    }
  }

  async function loadProducts() {
    loading.value = true;
    try {
      const payload = await productsService.listProducts(
        currentPage.value, currentKeyword.value,
        currentActive.value, "", currentSyncStatus.value,
        currentFeatured.value, currentItemNo.value, "",
        currentSortBy.value, currentSortOrder.value,
      );
      products.value = payload.items;
      total.value = payload.total;
      totalActive.value = payload.totalActive;
      totalInactive.value = payload.totalInactive;
      pageSize.value = payload.pageSize;
      if (selectedProduct.value) {
        const nextSelected = payload.items.find((item) => item.id === selectedProduct.value?.id) || null;
        selectedProduct.value = nextSelected;
        drawerVisible.value = nextSelected !== null;
      }
    } finally {
      loading.value = false;
    }
  }

  function openDetail(product: ProductListItem) {
    selectedProduct.value = product;
    drawerVisible.value = true;
  }

  function closeDetail() {
    selectedProduct.value = null;
    drawerVisible.value = false;
  }

  async function submitSearch() {
    await router.replace({
      query: buildQuery(
        1, searchDraft.value.trim(), filterActive.value,
        filterSyncStatus.value, filterFeatured.value,
        filterItemNo.value.trim(), "", filterStockLevel.value,
        currentSortBy.value, currentSortOrder.value,
      ),
    });
  }

  async function resetFilters() {
    searchDraft.value = "";
    filterActive.value = "1";
    filterSyncStatus.value = "";
    filterFeatured.value = false;
    filterItemNo.value = "";
    filterStockLevel.value = "";
    await router.replace({ query: { is_active: "1" } });
  }

  async function changePage(page: number) {
    await router.replace({
      query: buildQuery(
        page, currentKeyword.value, route.query.is_active !== undefined ? String(route.query.is_active) : "1",
        currentSyncStatus.value, currentFeatured.value,
        currentItemNo.value, "", currentStockLevel.value,
        currentSortBy.value, currentSortOrder.value,
      ),
    });
  }

  async function toggleProduct(product: ProductListItem) {
    togglingId.value = product.id;
    try {
      const result = await productsService.toggleProductActive(product.id);
      ElMessage.success(`${result.title}已${result.is_active ? "上架" : "下架"}`);
      await loadProducts();
    } finally {
      togglingId.value = 0;
    }
  }

  async function runReconcile(): Promise<ReconcileResult | null> {
    reconciling.value = true;
    try {
      const result = await productsService.reconcileProducts();
      if (result.deactivated > 0) {
        ElMessage.warning(`对账完成：下架 ${result.deactivated} 条商品`);
      } else {
        ElMessage.success(`对账完成：全部对齐，无需下架`);
      }
      await loadProducts();
      return result;
    } catch (err) {
      ElMessage.error("对账失败，请检查网络或后台日志");
      return null;
    } finally {
      reconciling.value = false;
    }
  }

  function buildQuery(
    page: number,
    keyword: string,
    isActive: string = "",
    syncStatus: string = "",
    featuredOnly: boolean = false,
    itemNo: string = "",
    kw: string = "",
    stockLevel: string = "",
    sortBy: string = "",
    sortOrder: string = "",
  ): Record<string, string> {
    const query: Record<string, string> = {};
    if (page > 1) query.page = String(page);
    if (keyword) query.keyword = keyword;
    if (isActive) query.is_active = isActive;
    if (syncStatus) query.vector_sync_status = syncStatus;
    if (featuredOnly) query.featured = "1";
    if (itemNo) query.item_no = itemNo;
    if (kw) query.kw = kw;
    if (stockLevel) query.stock_level = stockLevel;
    if (sortBy) query.sort_by = sortBy;
    if (sortOrder) query.sort_order = sortOrder;
    return query;
  }

  async function handleSortChange({ prop, order }: { prop: string; order: string | null }) {
    const sortBy = order ? prop : "";
    const sortOrder = order === "ascending" ? "asc" : order === "descending" ? "desc" : "";
    await router.replace({
      query: buildQuery(
        1, currentKeyword.value, route.query.is_active !== undefined ? String(route.query.is_active) : "1",
        currentSyncStatus.value, currentFeatured.value,
        currentItemNo.value, "", currentStockLevel.value,
        sortBy, sortOrder,
      ),
    });
  }

  watch(
    () => route.query,
    async () => {
      searchDraft.value = currentKeyword.value;
      filterActive.value = route.query.is_active !== undefined ? String(route.query.is_active) : "1";
      filterSyncStatus.value = currentSyncStatus.value;
      filterFeatured.value = currentFeatured.value;
      filterItemNo.value = currentItemNo.value;
      filterStockLevel.value = currentStockLevel.value;
      await Promise.all([loadFeaturedTitles(), loadProducts()]);
    },
    { immediate: true },
  );
  return {
    loading,
    togglingId,
    reconciling,
    drawerVisible,
    products,
    total,
    totalActive,
    totalInactive,
    pageSize,
    selectedProduct,
    searchDraft,
    filterActive,
    filterSyncStatus,
    filterFeatured,
    filterItemNo,
    filterStockLevel,
    currentPage,
    activeCount,
    tableRows,
    displayedTableRows,
    featuredTitles,
    togglingFeaturedId,
    openDetail,
    closeDetail,
    submitSearch,
    resetFilters,
    changePage,
    toggleProduct,
    toggleFeatured,
    runReconcile,
    handleSortChange,
  };
}

function formatSyncStatus(status: string): string {
  if (status === "success") {
    return "已入向量";
  }
  if (status === "failed") {
    return "同步失败";
  }
  if (status === "syncing") {
    return "同步中";
  }
  if (status === "pending") {
    return "待同步";
  }
  return "未记录";
}
