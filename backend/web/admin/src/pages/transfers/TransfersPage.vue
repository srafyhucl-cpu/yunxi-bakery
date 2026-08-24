<script setup lang="ts">
import { Refresh, Search } from "@element-plus/icons-vue";
import { computed, onMounted, onUnmounted, ref } from "vue";

import TransferDetailDrawer from "@/features/transfers/TransferDetailDrawer.vue";
import { useTransfersPage } from "./useTransfersPage";

const {
  loading,
  actionLoadingId,
  detailLoading,
  replySending,
  drawerVisible,
  replyDraft,
  transfers,
  selectedTransfer,
  sessionMessages,
  pendingCount,
  acceptedCount,
  listRows,
  normalizeRole,
  loadTransfers,
  openDetail,
  closeDrawer,
  acceptSelectedTransfer,
  closeSelectedTransfer,
  sendReply,
} = useTransfersPage();

const totalCount = computed(() => transfers.value.length);

onMounted(async () => {
  await loadTransfers();
});

function updateReplyDraft(value: string) {
  replyDraft.value = value;
}

// ── 前端筛选与检索逻辑 ──
const filterStatus = ref<"all" | "pending" | "accepted">("all");
const searchKeyword = ref("");

const filteredRows = computed(() => {
  let rows = listRows.value;
  if (filterStatus.value !== "all") {
    rows = rows.filter((row) => row.status === filterStatus.value);
  }
  if (searchKeyword.value.trim()) {
    const kw = searchKeyword.value.toLowerCase().trim();
    rows = rows.filter(
      (row) =>
        row.userId.toLowerCase().includes(kw) ||
        (row.reason && row.reason.toLowerCase().includes(kw)) ||
        (row.conversationSummary && row.conversationSummary.toLowerCase().includes(kw)),
    );
  }
  return rows;
});

// ── 表格高度自适应 ──
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
  <section class="transfers-page" data-testid="transfers-page">
    <!-- 单卡片占满整页 -->
    <el-card shadow="never" class="transfers-page__card">
      <!-- 卡片头：标题 + 统计快捷切换 Tab -->
      <template #header>
        <div class="transfers-page__card-header">
          <div class="transfers-page__header-left">
            <span class="transfers-page__page-title">转人工队列</span>
            <div class="transfers-page__stat-tabs">
              <button
                class="transfers-page__stat-tab"
                :class="{ 'is-active': filterStatus === 'all' }"
                type="button"
                data-testid="transfers-filter-all"
                @click="filterStatus = 'all'"
              >
                全部队列&nbsp;<strong>{{ totalCount }}</strong>
              </button>
              <button
                class="transfers-page__stat-tab transfers-page__stat-tab--warning"
                :class="{ 'is-active': filterStatus === 'pending' }"
                type="button"
                data-testid="transfers-filter-pending"
                @click="filterStatus = 'pending'"
              >
                待处理&nbsp;<strong>{{ pendingCount }}</strong>
              </button>
              <button
                class="transfers-page__stat-tab transfers-page__stat-tab--success"
                :class="{ 'is-active': filterStatus === 'accepted' }"
                type="button"
                data-testid="transfers-filter-accepted"
                @click="filterStatus = 'accepted'"
              >
                已接单&nbsp;<strong>{{ acceptedCount }}</strong>
              </button>
            </div>
          </div>
          <span class="transfers-page__card-total">共 {{ filteredRows.length }} 条记录</span>
        </div>
      </template>

      <!-- 紧凑单行筛选工具栏 -->
      <div class="transfers-page__toolbar">
        <div class="transfers-page__toolbar-left">
          <el-input
            v-model="searchKeyword"
            placeholder="检索用户ID、原委或摘要"
            clearable
            class="transfers-page__search"
            data-testid="transfers-search-input"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>

          <el-select v-model="filterStatus" style="width: 110px">
            <el-option label="全部状态" value="all" />
            <el-option label="待处理" value="pending" />
            <el-option label="已接单" value="accepted" />
          </el-select>
        </div>

        <div class="transfers-page__toolbar-right">
          <el-button
            :loading="loading"
            :icon="Refresh"
            type="primary"
            data-testid="transfers-refresh"
            @click="loadTransfers"
          >
            刷新队列
          </el-button>
        </div>
      </div>

      <!-- PC 桌面端表格 -->
      <div class="transfers-page__desktop" ref="tableWrapper">
        <el-table
          :data="filteredRows"
          v-loading="loading"
          stripe
          border
          :height="tableHeight"
          class="transfers-page__table"
          data-testid="transfers-table"
        >
          <el-table-column type="index" label="序号" width="60" align="center" />
          <el-table-column prop="shortUserId" label="用户标识" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="transfers-page__mono">{{ row.shortUserId }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="转人工原因" min-width="200" show-overflow-tooltip />
          <el-table-column prop="conversationSummary" label="前置会话摘要" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.conversationSummary">{{ row.conversationSummary }}</span>
              <span v-else class="transfers-page__empty">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="statusLabel" label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'accepted' ? 'success' : 'warning'" effect="light" size="small">
                <span :data-testid="`transfers-row-status-${row.id}`">{{ row.statusLabel }}</span>
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="createdAt" label="请求时间" width="170" align="center">
            <template #default="{ row }">
              {{ row.createdAt ? row.createdAt.replace("T", " ").slice(0, 19) : "未记录" }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right" align="center">
            <template #default="{ row }">
              <div class="transfers-page__actions" :data-testid="`transfers-row-${row.id}`">
                <el-button
                  link
                  type="primary"
                  :data-testid="`transfers-open-detail-${row.id}`"
                  @click="openDetail(row)"
                >
                  查看详情
                </el-button>
                <el-button
                  size="small"
                  type="success"
                  plain
                  :disabled="row.status !== 'pending'"
                  :loading="actionLoadingId === row.id && row.status === 'pending'"
                  :data-testid="`transfers-process-${row.id}`"
                  @click="openDetail(row)"
                >
                  处理
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 移动端卡片列表 -->
      <div class="transfers-page__mobile">
        <el-skeleton :rows="4" animated v-if="loading" />
        <div v-else class="transfers-page__cards">
          <button
            v-for="row in filteredRows"
            :key="row.id"
            type="button"
            class="transfers-page__card-item"
            :data-testid="`transfers-mobile-row-${row.id}`"
            @click="openDetail(row)"
          >
            <div class="transfers-page__card-top">
              <strong>{{ row.shortUserId }}</strong>
              <el-tag size="small" :type="row.status === 'accepted' ? 'success' : 'warning'" effect="light">
                {{ row.statusLabel }}
              </el-tag>
            </div>
            <div class="transfers-page__card-meta">
              <span>原因: {{ row.reason }}</span>
              <span v-if="row.conversationSummary">摘要: {{ row.conversationSummary }}</span>
              <span>时间: {{ row.createdAt ? row.createdAt.replace("T", " ").slice(0, 16) : "未记录" }}</span>
            </div>
          </button>
        </div>
      </div>

      <!-- 空状态 -->
      <el-empty
        v-if="!loading && filteredRows.length === 0"
        description="当前队列没有待处理的转人工请求"
        style="padding: 60px 0"
      />
    </el-card>

    <TransferDetailDrawer
      :visible="drawerVisible"
      :transfer="selectedTransfer"
      :loading="detailLoading"
      :action-loading-id="actionLoadingId"
      :reply-sending="replySending"
      :reply-draft="replyDraft"
      :messages="sessionMessages"
      :normalize-role="normalizeRole"
      @update:visible="($event) => (!$event ? closeDrawer() : null)"
      @update:reply-draft="updateReplyDraft"
      @accept="acceptSelectedTransfer"
      @close="closeSelectedTransfer"
      @send-reply="sendReply"
    />
  </section>
</template>

<style scoped>
/* ── 页面根容器 ── */
.transfers-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── 单主卡片：铺满剩余高度 ── */
.transfers-page__card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.transfers-page__card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

/* ── 卡片头 ── */
.transfers-page__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
}

.transfers-page__header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
  flex-wrap: wrap;
}

.transfers-page__page-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--yx-text);
  white-space: nowrap;
}

/* ── 统计快捷 Tab ── */
.transfers-page__stat-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
}

.transfers-page__stat-tab {
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

.transfers-page__stat-tab strong {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: var(--yx-text);
}

.transfers-page__stat-tab:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.transfers-page__stat-tab.is-active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.transfers-page__stat-tab.is-active strong {
  color: var(--el-color-primary);
}

.transfers-page__stat-tab--success.is-active {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.transfers-page__stat-tab--success.is-active strong {
  color: var(--el-color-success);
}

.transfers-page__stat-tab--warning.is-active {
  border-color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}

.transfers-page__stat-tab--warning.is-active strong {
  color: var(--el-color-warning);
}

.transfers-page__card-total {
  font-size: 13px;
  color: var(--yx-text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

/* ── 工具栏：筛选项单行 ── */
.transfers-page__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-wrap: wrap;
  flex-shrink: 0;
}

.transfers-page__toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.transfers-page__search {
  width: 240px;
}

.transfers-page__toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ── 桌面端表格区 ── */
.transfers-page__desktop {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.transfers-page__mobile {
  display: none;
}

/* ── 表格样式 ── */
.transfers-page__table {
  flex: 1;
  --el-table-text-color: var(--yx-text);
}

.transfers-page__table :deep(.el-table__header th) {
  padding: 10px 0;
  text-align: center;
}

.transfers-page__table :deep(.el-table__header th .cell) {
  white-space: nowrap;
}

.transfers-page__table :deep(.el-table__row td) {
  padding: 14px 0;
}

.transfers-page__table :deep(.el-table__cell) {
  vertical-align: middle;
}

/* ── 样式细节 ── */
.transfers-page__mono {
  font-family: var(--yx-font-mono), monospace;
  font-size: 13px;
  color: var(--yx-text);
}

.transfers-page__empty {
  color: var(--yx-text-muted);
}

.transfers-page__actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

/* ── 移动端卡片视图 ── */
@media (max-width: 767px) {
  .transfers-page__toolbar {
    padding: 12px 16px;
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }

  .transfers-page__toolbar-left {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    width: 100%;
  }

  .transfers-page__toolbar-left > .transfers-page__search {
    grid-column: 1 / -1;
    width: 100% !important;
  }

  .transfers-page__toolbar-left .el-select {
    width: 100% !important;
  }

  .transfers-page__toolbar-right {
    width: 100%;
  }

  .transfers-page__toolbar-right .el-button {
    width: 100%;
  }

  .transfers-page__desktop {
    display: none;
  }

  .transfers-page__mobile {
    display: block;
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
  }

  .transfers-page__cards {
    display: grid;
    gap: 10px;
  }

  .transfers-page__card-item {
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

  .transfers-page__card-item:active {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }

  .transfers-page__card-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    font-size: 14px;
    font-weight: 600;
    color: var(--yx-text);
  }

  .transfers-page__card-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    font-size: 12px;
    color: var(--yx-text-muted);
  }
}
</style>
