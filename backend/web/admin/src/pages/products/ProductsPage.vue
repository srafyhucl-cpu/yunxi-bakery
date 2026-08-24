<script setup lang="ts">
import { QuestionFilled, Refresh, Search } from "@element-plus/icons-vue";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";

import ProductDetailDrawer from "@/features/products/ProductDetailDrawer.vue";
import { useProductsPage } from "./useProductsPage";

const route = useRoute();

const {
  loading,
  togglingId,
  drawerVisible,
  selectedProduct,
  searchDraft,
  filterActive,
  filterSyncStatus,
  filterFeatured,
  filterItemNo,
  filterStockLevel,
  currentPage,
  total,
  totalActive,
  totalInactive,
  pageSize,
  activeCount,
  displayedTableRows,
  togglingFeaturedId,
  openDetail,
  closeDetail,
  submitSearch,
  resetFilters,
  changePage,
  toggleProduct,
  toggleFeatured,
  reconciling,
  runReconcile,
  handleSortChange,
} = useProductsPage();

const inactiveCount = computed(
  () => displayedTableRows.value.filter((row) => !row.isActive).length,
);

const tableWrapper = ref<HTMLElement | null>(null);
const tableHeight = ref(400);
let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  if (tableWrapper.value) {
    resizeObserver = new ResizeObserver(() => {
      tableHeight.value = tableWrapper.value?.clientHeight ?? 400;
    });
    resizeObserver.observe(tableWrapper.value);
    tableHeight.value = tableWrapper.value.clientHeight;
  }
});

onUnmounted(() => {
  resizeObserver?.disconnect();
});
</script>

<template>
  <section class="products-page" data-testid="products-page">
    <!-- 单卡片占满整页 -->
    <el-card shadow="never" class="products-page__card">
      <!-- 卡片头：标题 + 统计快捷切换 Tab + 总条数 -->
      <template #header>
        <div class="products-page__card-header">
          <div class="products-page__header-left">
            <span class="products-page__page-title">商品列表</span>
            <div class="products-page__stat-tabs">
              <button
                class="products-page__stat-tab"
                :class="{ 'is-active': filterActive === 'all' }"
                type="button"
                data-testid="products-filter-all"
                @click="filterActive = 'all'; submitSearch()"
              >
                全部商品&nbsp;<strong>{{ totalActive + totalInactive }}</strong>
              </button>
              <button
                class="products-page__stat-tab products-page__stat-tab--success"
                :class="{ 'is-active': filterActive === '1' }"
                type="button"
                data-testid="products-filter-active"
                @click="filterActive = '1'; submitSearch()"
              >
                在售中&nbsp;<strong>{{ totalActive }}</strong>
              </button>
              <button
                class="products-page__stat-tab products-page__stat-tab--warning"
                :class="{ 'is-active': filterActive === '0' }"
                type="button"
                data-testid="products-filter-inactive"
                @click="filterActive = '0'; submitSearch()"
              >
                已下架&nbsp;<strong>{{ totalInactive }}</strong>
              </button>
            </div>
          </div>
          <span class="products-page__card-total">共 {{ total }} 条</span>
        </div>
      </template>

      <!-- 紧凑单行筛选工具栏 -->
      <div class="products-page__toolbar">
        <div class="products-page__toolbar-left">
          <el-input
            v-model="searchDraft"
            placeholder="搜索商品标题"
            clearable
            class="products-page__search"
            data-testid="products-search-input"
            @keyup.enter="submitSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>

          <el-select v-model="filterActive" clearable style="width: 110px">
            <el-option label="全部状态" value="all" />
            <el-option label="在售" value="1" />
            <el-option label="已下架" value="0" />
          </el-select>

          <el-select
            v-model="filterSyncStatus"
            placeholder="AI 可读"
            clearable
            style="width: 110px"
          >
            <el-option label="全部" value="" />
            <el-option label="已入向量" value="success" />
            <el-option label="待同步" value="pending" />
            <el-option label="同步失败" value="failed" />
            <el-option label="同步中" value="syncing" />
          </el-select>

          <el-select
            v-model="filterStockLevel"
            placeholder="库存"
            clearable
            style="width: 105px"
          >
            <el-option label="全部" value="" />
            <el-option label="充足（>200）" value="sufficient" />
            <el-option label="偏少（≤200）" value="low" />
            <el-option label="无库存" value="zero" />
          </el-select>

          <el-input
            v-model="filterItemNo"
            placeholder="商品编码"
            clearable
            style="width: 150px"
          />

          <el-checkbox v-model="filterFeatured" border style="height: 32px">
            仅主推款
          </el-checkbox>
        </div>

        <div class="products-page__toolbar-right">
          <el-button type="primary" :icon="Search" data-testid="products-search-submit" @click="submitSearch">
            筛选
          </el-button>
          <el-button data-testid="products-reset-filters" @click="resetFilters">重置</el-button>
          <el-button
            type="warning"
            :loading="reconciling"
            :icon="Refresh"
            @click="runReconcile"
          >
            全量对账
          </el-button>
        </div>
      </div>

      <!-- PC 桌面端表格 -->
      <div class="products-page__desktop" ref="tableWrapper">
        <el-table
          :data="displayedTableRows"
          v-loading="loading"
          stripe
          border
          :height="tableHeight"
          class="products-page__table"
          data-testid="products-table"
          :default-sort="
            route.query.sort_by
              ? {
                  prop: String(route.query.sort_by),
                  order:
                    route.query.sort_order === 'asc'
                      ? 'ascending'
                      : 'descending',
                }
              : { prop: 'updatedAt', order: 'descending' }
          "
          @sort-change="handleSortChange"
        >
          <el-table-column type="index" label="序号" width="60" align="center" />

          <el-table-column
            prop="title"
            label="商品名"
            min-width="200"
            sortable="custom"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <button
                class="products-page__title-btn"
                type="button"
                :data-testid="`products-row-title-${row.youzanItemId || row.id}`"
                @click="openDetail(row)"
              >
                {{ row.title || '（无标题）' }}
              </button>
            </template>
          </el-table-column>

          <el-table-column prop="activeLabel" label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag
                :type="row.isActive ? 'success' : 'info'"
                effect="light"
                size="small"
              >
                {{ row.activeLabel }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column
            prop="vectorSyncStatus"
            label="AI 可读"
            width="90"
            align="center"
            sortable="custom"
          >
            <template #default="{ row }">
              {{ row.syncStatusLabel }}
            </template>
          </el-table-column>

          <el-table-column
            prop="itemNo"
            label="商品编码"
            width="170"
            align="center"
            sortable="custom"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <span v-if="row.itemNo" class="products-page__mono">{{ row.itemNo }}</span>
              <span v-else class="products-page__empty">—</span>
            </template>
          </el-table-column>

          <el-table-column
            prop="priceFen"
            label="单价"
            width="90"
            align="right"
            sortable="custom"
          >
            <template #default="{ row }">
              <span v-if="row.priceFen != null" class="products-page__price">
                ¥{{ (row.priceFen / 100).toFixed(2) }}
              </span>
              <span v-else class="products-page__empty">—</span>
            </template>
          </el-table-column>

          <el-table-column prop="stock" width="100" align="center" sortable="custom">
            <template #header>
              <el-tooltip content="库存 > 200 显示「充足」" placement="top">
                <el-icon style="margin-right: 3px; vertical-align: middle; cursor: help; color: var(--el-color-info)">
                  <QuestionFilled />
                </el-icon>
              </el-tooltip>
              <span>库存</span>
            </template>
            <template #default="{ row }">
              <span v-if="row.stock == null" class="products-page__empty">—</span>
              <el-tooltip
                v-else-if="row.stock > 200"
                :content="`实际库存：${row.stock.toLocaleString()} 件`"
                placement="top"
              >
                <span class="products-page__stock-ok">充足</span>
              </el-tooltip>
              <span v-else class="products-page__stock">
                {{ row.stock.toLocaleString() }}
              </span>
            </template>
          </el-table-column>

          <el-table-column
            prop="soldNum"
            label="销量"
            width="80"
            align="center"
            sortable="custom"
          >
            <template #default="{ row }">
              <span v-if="row.soldNum" class="products-page__sold">
                {{ row.soldNum.toLocaleString() }}
              </span>
              <span v-else class="products-page__empty">—</span>
            </template>
          </el-table-column>

          <el-table-column
            prop="updatedAt"
            label="最近更新"
            min-width="160"
            align="center"
            sortable="custom"
          >
            <template #default="{ row }">
              {{ row.updatedAt ? row.updatedAt.replace('T', ' ').slice(0, 19) : '未记录' }}
            </template>
          </el-table-column>

          <el-table-column label="操作" width="200" fixed="right" align="center">
            <template #default="{ row }">
              <div class="products-page__actions">
                <el-tooltip
                  :content="row.isFeatured ? '移出主推款' : '加入主推款'"
                  placement="top"
                >
                  <el-switch
                    :model-value="row.isFeatured"
                    :loading="togglingFeaturedId === row.id"
                    size="small"
                    active-color="#f59e0b"
                    @change="toggleFeatured(row)"
                  />
                </el-tooltip>
                <el-button link type="primary" @click="openDetail(row)">查看</el-button>
                <el-button
                  :loading="togglingId === row.id"
                  :type="row.isActive ? 'warning' : 'success'"
                  plain
                  size="small"
                  :data-testid="`products-toggle-active-${row.youzanItemId || row.id}`"
                  @click="toggleProduct(row)"
                >
                  {{ row.isActive ? '下架' : '上架' }}
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 移动端卡片列表 -->
      <div class="products-page__mobile">
        <el-skeleton :rows="4" animated v-if="loading" />
        <div v-else class="products-page__cards">
          <button
            v-for="row in displayedTableRows"
            :key="row.id"
            class="products-page__card-item"
            type="button"
            :data-testid="`products-mobile-row-${row.youzanItemId || row.id}`"
            @click="openDetail(row)"
          >
            <div class="products-page__card-top">
              <strong>{{ row.title }}</strong>
              <el-tag size="small" :type="row.isActive ? 'success' : 'info'" effect="light">
                {{ row.activeLabel }}
              </el-tag>
            </div>
            <div class="products-page__card-meta">
              <span v-if="row.priceFen != null" class="products-page__price">
                ¥{{ (row.priceFen / 100).toFixed(2) }}
              </span>
              <span v-if="row.soldNum">销量 {{ row.soldNum.toLocaleString() }}</span>
              <span v-if="row.itemNo" class="products-page__mono">{{ row.itemNo }}</span>
              <span>{{ row.syncStatusLabel }}</span>
              <span>{{ row.updatedAt ? row.updatedAt.slice(0, 10) : '未记录' }}</span>
            </div>
          </button>
        </div>
      </div>

      <!-- 分页栏 -->
      <div class="products-page__pagination">
        <div class="products-page__page-stats">
          <span>当前页 <strong>{{ displayedTableRows.length }}</strong> 条</span>
          <span class="products-page__divider" />
          <span>在售 <strong class="is-success">{{ activeCount }}</strong></span>
          <span class="products-page__divider" />
          <span>下架 <strong>{{ inactiveCount }}</strong></span>
        </div>
        <el-pagination
          background
          layout="prev, pager, next"
          :current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          @current-change="changePage"
        />
      </div>
    </el-card>

    <ProductDetailDrawer
      v-model:visible="drawerVisible"
      :product="selectedProduct"
      :toggling-id="togglingId"
      @toggle="toggleProduct"
      @update:visible="($event) => (!$event ? closeDetail() : null)"
    />
  </section>
</template>

<style scoped>
/* ── 页面根容器 ── */
.products-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── 单主卡片：铺满剩余高度 ── */
.products-page__card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.products-page__card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

/* ── 卡片头 ── */
.products-page__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
}

.products-page__header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
  flex-wrap: wrap;
}

.products-page__page-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--yx-text);
  white-space: nowrap;
}

/* ── 统计快捷 Tab ── */
.products-page__stat-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
}

.products-page__stat-tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 20px;
  background: transparent;
  font-size: 13px;
  color: var(--yx-text-muted);
  cursor: pointer;
  transition: all 0.18s ease;
  white-space: nowrap;
}

.products-page__stat-tab strong {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: var(--yx-text);
}

.products-page__stat-tab:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.products-page__stat-tab.is-active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.products-page__stat-tab.is-active strong {
  color: var(--el-color-primary);
}

.products-page__stat-tab--success.is-active {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.products-page__stat-tab--success.is-active strong {
  color: var(--el-color-success);
}

.products-page__stat-tab--warning.is-active {
  border-color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}

.products-page__stat-tab--warning.is-active strong {
  color: var(--el-color-warning);
}

.products-page__card-total {
  font-size: 13px;
  color: var(--yx-text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

/* ── 工具栏：筛选项单行 ── */
.products-page__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-wrap: wrap;
  flex-shrink: 0;
}

.products-page__toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.products-page__search {
  width: 200px;
}

.products-page__toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ── 桌面端表格区 ── */
.products-page__desktop {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.products-page__mobile {
  display: none;
}

/* ── 表格样式 ── */
.products-page__table {
  flex: 1;
  --el-table-text-color: var(--yx-text);
}

.products-page__table :deep(.el-table__header th) {
  padding: 10px 0;
  text-align: center;
}

.products-page__table :deep(.el-table__header th .cell) {
  white-space: nowrap;
}

/* 行高 48px：内容约 20px + 上下各 14px = 48px */
.products-page__table :deep(.el-table__row td) {
  padding: 14px 0;
}

.products-page__table :deep(.el-table__cell) {
  vertical-align: middle;
}

/* ── 单元格样式 ── */
.products-page__title-btn {
  width: 100%;
  border: 0;
  background: transparent;
  padding: 0;
  text-align: left;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
  color: var(--el-color-primary);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  display: block;
  transition: color 0.15s;
}

.products-page__title-btn:hover {
  color: var(--el-color-primary-dark-2);
}

.products-page__price {
  font-variant-numeric: tabular-nums;
  font-size: 13px;
  color: var(--yx-text);
}

.products-page__stock {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  font-size: 13px;
  color: var(--yx-text);
}

.products-page__stock-ok {
  font-size: 13px;
  color: var(--yx-text);
}

.products-page__sold {
  font-variant-numeric: tabular-nums;
  font-size: 13px;
  color: var(--yx-text);
}

.products-page__mono {
  font-size: 13px;
  color: var(--yx-text);
  font-variant-numeric: tabular-nums;
}

.products-page__empty {
  color: var(--yx-text);
  font-size: 13px;
}

.products-page__actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: nowrap;
}

/* ── 分页栏 ── */
.products-page__pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  flex-shrink: 0;
}

.products-page__page-stats {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--yx-text-muted);
  white-space: nowrap;
}

.products-page__page-stats strong {
  font-variant-numeric: tabular-nums;
  color: var(--yx-text);
}

.products-page__page-stats strong.is-success {
  color: var(--el-color-success);
}

.products-page__divider {
  display: inline-block;
  width: 1px;
  height: 14px;
  background: var(--el-border-color);
}

/* ── 移动端卡片视图 ── */
@media (max-width: 767px) {
  .products-page__toolbar {
    padding: 12px 16px;
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }

  .products-page__toolbar-left {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    width: 100%;
  }

  /* 搜索框独占满宽 */
  .products-page__toolbar-left > :first-child {
    grid-column: 1 / -1;
  }

  /* 强制覆盖所有内联的 width: 110px */
  .products-page__toolbar-left .el-select,
  .products-page__toolbar-left .el-input,
  .products-page__toolbar-left .el-checkbox {
    width: 100% !important;
  }

  .products-page__toolbar-right {
    width: 100%;
    justify-content: space-between;
  }

  .products-page__desktop {
    display: none;
  }

  .products-page__mobile {
    display: block;
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
  }

  .products-page__cards {
    display: grid;
    gap: 10px;
  }

  .products-page__card-item {
    width: 100%;
    display: grid;
    gap: 8px;
    padding: 14px;
    border: 1px solid var(--yx-border);
    border-radius: 12px;
    background: transparent;
    text-align: left;
    cursor: pointer;
    transition: box-shadow 0.18s;
  }

  .products-page__card-item:active {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }

  .products-page__card-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    font-size: 14px;
    font-weight: 600;
    color: var(--yx-text);
  }

  .products-page__card-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    font-size: 12px;
    color: var(--yx-text-muted);
  }

  .products-page__pagination {
    justify-content: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .products-page__page-stats {
    display: none;
  }
}
</style>
