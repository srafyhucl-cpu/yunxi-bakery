<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { Search } from "@element-plus/icons-vue";

import { useKnowledgePage } from "./useKnowledgePage";

const {
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
  totalActive,
  totalFailed,
  pageSize,
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
} = useKnowledgePage();

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
  <section class="knowledge-page">
    <el-card shadow="never" class="knowledge-page__card">
      <template #header>
        <div class="knowledge-page__card-header">
          <div class="knowledge-page__header-left">
            <span class="knowledge-page__page-title">知识配置</span>
            <div class="knowledge-page__stat-tabs">
              <button
                class="knowledge-page__stat-tab"
                :class="{ 'is-active': filterDraft.isActive === '' && filterDraft.vectorStatus === '' }"
                type="button"
                @click="filterDraft.isActive = ''; filterDraft.vectorStatus = ''; submitFilters()"
              >
                全部知识&nbsp;<strong>{{ total }}</strong>
              </button>
              <button
                class="knowledge-page__stat-tab knowledge-page__stat-tab--success"
                :class="{ 'is-active': filterDraft.isActive === '1' }"
                type="button"
                @click="filterDraft.isActive = '1'; filterDraft.vectorStatus = ''; submitFilters()"
              >
                已启用&nbsp;<strong>{{ totalActive }}</strong>
              </button>
              <button
                class="knowledge-page__stat-tab knowledge-page__stat-tab--danger"
                :class="{ 'is-active': filterDraft.vectorStatus === 'failed' }"
                type="button"
                @click="filterDraft.isActive = ''; filterDraft.vectorStatus = 'failed'; submitFilters()"
              >
                已失败&nbsp;<strong>{{ totalFailed }}</strong>
              </button>
            </div>
          </div>
          <div class="knowledge-page__header-right">
            <span class="knowledge-page__card-total">共 {{ total }} 条</span>
            <el-button type="primary" @click="openCreate">新增知识</el-button>
          </div>
        </div>
      </template>

      <!-- 紧凑单行筛选工具栏 -->
      <div class="knowledge-page__toolbar">
        <div class="knowledge-page__toolbar-left">
          <el-input
            v-model="filterDraft.keyword"
            clearable
            placeholder="搜索标题、内容或关键词"
            class="knowledge-page__search"
            @keyup.enter="submitFilters"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>

          <el-select v-model="filterDraft.contentType" clearable placeholder="全部内容类型" style="width: 130px">
            <el-option label="FAQ" value="faq" />
            <el-option label="规则" value="rule" />
            <el-option label="话术" value="script" />
          </el-select>

          <el-select v-model="filterDraft.isActive" clearable placeholder="全部状态" style="width: 110px">
            <el-option label="启用" value="1" />
            <el-option label="停用" value="0" />
          </el-select>

          <el-select v-model="filterDraft.vectorStatus" clearable placeholder="全部同步状态" style="width: 140px">
            <el-option label="已入向量" value="success" />
            <el-option label="待同步" value="pending" />
            <el-option label="同步失败" value="failed" />
            <el-option label="同步中" value="syncing" />
          </el-select>
        </div>
        <div class="knowledge-page__toolbar-right">
          <el-button type="primary" @click="submitFilters">筛选</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>
      </div>

      <el-alert
        v-if="errorMessage"
        class="knowledge-page__alert"
        type="error"
        show-icon
        :closable="false"
      >
        <template #title>
          <span>{{ errorMessage }}</span>
          <el-button link type="primary" @click="loadEntries">重试</el-button>
        </template>
      </el-alert>

      <div class="knowledge-page__desktop" ref="tableWrapper">
        <el-table :data="rows" v-loading="loading" :height="tableHeight" class="knowledge-page__table" stripe>
          <el-table-column type="index" label="序号" width="60" align="center" />
          <el-table-column prop="title" label="知识条目" min-width="260" header-align="center" align="left">
            <template #default="{ row }">
              <button class="knowledge-page__title-button" type="button" @click="openEdit(row)">
                <strong>{{ row.title }}</strong>
                <span>{{ row.content }}</span>
              </button>
            </template>
          </el-table-column>
          <el-table-column prop="typeLabel" label="类型" width="120" align="center" />
          <el-table-column prop="audienceLabel" label="可见范围" width="110" align="center" />
          <el-table-column prop="reviewLabel" label="发布状态" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="row.reviewType" effect="light">{{ row.reviewLabel }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="validityLabel" label="有效期" min-width="180" align="center" />
          <el-table-column prop="activeLabel" label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.isActive ? 'success' : 'info'" effect="light">{{ row.activeLabel }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="syncLabel" label="AI 可读" width="120" align="center">
            <template #default="{ row }">
              <el-tag :type="row.syncType" effect="light">{{ row.syncLabel }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="updatedAtLabel" label="更新时间" min-width="170" align="center" />
          <el-table-column label="操作" width="230" fixed="right" align="center">
            <template #default="{ row }">
              <div class="knowledge-page__actions">
                <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
                <el-button
                  link
                  :type="row.isActive ? 'warning' : 'success'"
                  :loading="actionId === row.id"
                  @click="toggleEntry(row)"
                >
                  {{ row.isActive ? "停用" : "启用" }}
                </el-button>
                <el-button
                  v-if="row.vectorSyncStatus === 'failed'"
                  link
                  type="danger"
                  :loading="actionId === row.id"
                  @click="retrySync(row)"
                >
                  重试同步
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="knowledge-page__mobile">
        <el-skeleton v-if="loading" :rows="4" animated />
        <button
          v-for="row in rows"
          v-else
          :key="row.id"
          class="knowledge-page__card"
          type="button"
          @click="openEdit(row)"
        >
          <div>
            <strong>{{ row.title }}</strong>
            <el-tag size="small" :type="row.syncType">{{ row.syncLabel }}</el-tag>
          </div>
          <span>{{ row.typeLabel }} · {{ row.audienceLabel }} · {{ row.reviewLabel }} · {{ row.validityLabel }}</span>
        </button>
      </div>

      <el-empty v-if="!loading && rows.length === 0" description="当前筛选条件下没有知识条目" />

      <div class="knowledge-page__pagination">
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

    <el-drawer
      v-model="drawerVisible"
      :title="drawerMode === 'create' ? '新增知识' : '编辑知识'"
      size="560px"
      @closed="closeDrawer"
    >
      <el-form label-position="top" class="knowledge-page__drawer-form">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="例如：配送范围说明" />
        </el-form-item>
        <el-form-item label="内容类型">
          <div class="knowledge-page__inline-field">
            <el-select v-model="form.contentType">
              <el-option label="FAQ" value="faq" />
              <el-option label="规则" value="rule" />
              <el-option label="话术" value="script" />
            </el-select>
            <el-button plain @click="suggestCategory">AI 建议分类</el-button>
          </div>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="form.keywords" placeholder="用逗号分隔，便于检索" />
        </el-form-item>
        <div class="knowledge-page__drawer-row">
          <el-form-item label="可见范围">
            <el-select v-model="form.audience">
              <el-option label="共同可见" value="all" />
              <el-option label="客户机器人" value="customer" />
              <el-option label="员工助手" value="employee" />
            </el-select>
          </el-form-item>
          <el-form-item label="发布状态">
            <el-select v-model="form.reviewStatus">
              <el-option label="草稿" value="draft" />
              <el-option label="已发布" value="published" />
              <el-option label="已归档" value="archived" />
            </el-select>
          </el-form-item>
        </div>
        <div class="knowledge-page__drawer-row">
          <el-form-item label="生效开始">
            <el-date-picker
              v-model="form.validFrom"
              type="datetime"
              value-format="YYYY-MM-DD HH:mm:ss"
              placeholder="长期有效"
            />
          </el-form-item>
          <el-form-item label="生效截止">
            <el-date-picker
              v-model="form.validUntil"
              type="datetime"
              value-format="YYYY-MM-DD HH:mm:ss"
              placeholder="长期有效"
            />
          </el-form-item>
        </div>
        <el-form-item label="内容" required>
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="8"
            placeholder="写入客服回答时需要严格依据的内容"
          />
        </el-form-item>
        <div class="knowledge-page__drawer-row">
          <el-form-item label="优先级">
            <el-input-number v-model="form.priority" :min="0" :max="100" />
          </el-form-item>
          <el-form-item label="是否启用">
            <el-switch v-model="form.isActive" active-text="启用" inactive-text="停用" />
          </el-form-item>
        </div>
      </el-form>

      <el-alert
        v-if="selectedEntry?.vectorSyncError"
        type="error"
        show-icon
        :closable="false"
        :title="selectedEntry.vectorSyncError"
      />

      <section v-if="history.length" class="knowledge-page__history">
        <h4>最近变更</h4>
        <pre>{{ JSON.stringify(history.slice(0, 5), null, 2) }}</pre>
      </section>

      <template #footer>
        <div class="knowledge-page__drawer-actions">
          <el-button @click="drawerVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveEntry">保存</el-button>
        </div>
      </template>
    </el-drawer>
  </section>
</template>

<style scoped>
/* ── 页面根容器 ── */
.knowledge-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── 单主卡片：铺满剩余高度 ── */
.knowledge-page__card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.knowledge-page__card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

/* ── 卡片头 ── */
.knowledge-page__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
}

.knowledge-page__header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
  flex-wrap: wrap;
}

.knowledge-page__page-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--yx-text);
  white-space: nowrap;
}

.knowledge-page__header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ── 统计快捷 Tab ── */
.knowledge-page__stat-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
}

.knowledge-page__stat-tab {
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

.knowledge-page__stat-tab strong {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: var(--yx-text);
}

.knowledge-page__stat-tab:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.knowledge-page__stat-tab.is-active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.knowledge-page__stat-tab.is-active strong {
  color: var(--el-color-primary);
}

.knowledge-page__stat-tab--success.is-active {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.knowledge-page__stat-tab--success.is-active strong {
  color: var(--el-color-success);
}

.knowledge-page__stat-tab--danger.is-active {
  border-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.knowledge-page__stat-tab--danger.is-active strong {
  color: var(--el-color-danger);
}

.knowledge-page__card-total {
  font-size: 13px;
  color: var(--yx-text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

/* ── 工具栏：筛选项单行 ── */
.knowledge-page__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-wrap: wrap;
  flex-shrink: 0;
}

.knowledge-page__toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.knowledge-page__search {
  width: 220px;
}

.knowledge-page__toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ── 桌面端表格区 ── */
.knowledge-page__desktop {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.knowledge-page__mobile {
  display: none;
}

/* ── 表格样式 ── */
.knowledge-page__table {
  flex: 1;
  --el-table-text-color: var(--yx-text);
}

.knowledge-page__table :deep(.el-table__header th) {
  padding: 10px 0;
}

.knowledge-page__table :deep(.el-table__header th .cell) {
  white-space: nowrap;
}

.knowledge-page__table :deep(.el-table__row td) {
  padding: 14px 0;
}

.knowledge-page__table :deep(.el-table__cell) {
  vertical-align: middle;
}

.knowledge-page__title-button {
  width: 100%;
  border: 0;
  background: transparent;
  padding: 0;
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  overflow: hidden;
  max-width: 100%;
}

.knowledge-page__title-button strong {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-color-primary);
  transition: color 0.15s;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-page__title-button:hover strong {
  color: var(--el-color-primary-dark-2);
}

.knowledge-page__title-button span {
  font-size: 13px;
  color: var(--yx-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-page__actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: nowrap;
}

/* ── 分页栏 ── */
.knowledge-page__pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 10px 20px;
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  flex-shrink: 0;
}

/* ── 抽屉表单 ── */
.knowledge-page__drawer-form {
  display: grid;
  gap: 8px;
}

.knowledge-page__drawer-row {
  display: flex;
  gap: 12px;
}

.knowledge-page__drawer-row > * {
  flex: 1;
}

.knowledge-page__drawer-row :deep(.el-date-editor) {
  width: 100%;
}

.knowledge-page__inline-field {
  display: flex;
  gap: 12px;
  width: 100%;
}

.knowledge-page__inline-field .el-select {
  flex: 1;
}

.knowledge-page__history {
  margin-top: 18px;
}

.knowledge-page__history pre {
  max-height: 180px;
  overflow: auto;
  border-radius: 12px;
  padding: 12px;
  background: #f8fafc;
  font-size: 12px;
}

.knowledge-page__drawer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

/* ── 移动端卡片视图 ── */
@media (max-width: 767px) {
  .knowledge-page__toolbar {
    padding: 12px 16px;
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }

  .knowledge-page__toolbar-left {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    width: 100%;
  }

  .knowledge-page__toolbar-left > :first-child {
    grid-column: 1 / -1;
  }

  .knowledge-page__toolbar-left .el-select,
  .knowledge-page__toolbar-left .el-input {
    width: 100% !important;
  }

  .knowledge-page__toolbar-right {
    width: 100%;
    justify-content: space-between;
  }

  .knowledge-page__desktop {
    display: none;
  }

  .knowledge-page__mobile {
    display: block;
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
  }

  .knowledge-page__card {
    display: grid;
    gap: 8px;
    border: 1px solid var(--yx-border);
    border-radius: 12px;
    padding: 14px;
    background: transparent;
    text-align: left;
    cursor: pointer;
    transition: box-shadow 0.18s;
    width: 100%;
    margin-bottom: 10px;
  }

  .knowledge-page__card:active {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }

  .knowledge-page__card div {
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }

  .knowledge-page__card span {
    font-size: 13px;
    color: var(--yx-text-muted);
  }
}
</style>
