<script setup lang="ts">
import { Search } from "@element-plus/icons-vue";
import { reactive, ref, onMounted, onUnmounted } from "vue";

import ObservabilityDetailDrawer from "./ObservabilityDetailDrawer.vue";
import { useObservabilityWorkbench } from "./useObservabilityWorkbench";
import {
  formatSource,
  formatAction,
  formatEventType,
  formatEntityType,
  parseChangeSummary,
  parseWebhookSummary,
} from "@/utils/observabilityFormat";

import type { ObservabilityTab } from "@/types/observability";

const props = defineProps<{
  mode: "workspace" | "failures";
}>();

const page = reactive(useObservabilityWorkbench(props.mode));

const workspaceTabs: Array<{ key: ObservabilityTab; label: string }> = [
  { key: "history", label: "回写历史" },
  { key: "webhooks", label: "Webhook 审计" },
];

const failureTabs: Array<{ key: ObservabilityTab; label: string }> = [
  { key: "history", label: "失败回写" },
  { key: "webhooks", label: "失败 Webhook" },
];

function updateDrawerVisible(value: boolean) {
  if (!value) {
    page.closeDrawer();
  }
}

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

import { ElMessage } from "element-plus";

const errorDialogVisible = ref(false);
const activeErrorLog = ref("");

function openErrorDialog(log: string) {
  activeErrorLog.value = log;
  errorDialogVisible.value = true;
}

function copyErrorLog() {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(activeErrorLog.value)
      .then(() => {
        ElMessage.success("复制成功");
      })
      .catch(() => {
        ElMessage.error("复制失败");
      });
  } else {
    const textarea = document.createElement("textarea");
    textarea.value = activeErrorLog.value;
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand("copy");
      ElMessage.success("复制成功");
    } catch (err) {
      ElMessage.error("复制失败");
    }
    document.body.removeChild(textarea);
  }
}
</script>

<template>
  <section class="observability-page">
    <!-- 单卡片占满整页 -->
    <el-card shadow="never" class="observability-page__card">
      <!-- 卡片头：标题 + 统计快捷切换 Tab + 统计展示 -->
      <template #header>
        <div class="observability-page__card-header">
          <div class="observability-page__header-left">
            <span class="observability-page__page-title">
              {{ props.mode === "workspace" ? "数据观察台" : "失败排查" }}
            </span>
            <div class="observability-page__stat-tabs">
              <button
                v-for="tab in props.mode === 'workspace' ? workspaceTabs : failureTabs"
                :key="tab.key"
                class="observability-page__stat-tab"
                :class="{ 'is-active': page.activeTab === tab.key }"
                type="button"
                @click="page.switchTab(tab.key)"
              >
                {{ tab.label }}
              </button>
            </div>
          </div>
          <span class="observability-page__card-total">
            {{ page.summaryLabel }}：<strong>{{ page.total }}</strong>
            <span class="observability-page__divider-inline" />
            当前页：<strong>{{ page.listCount }}</strong>
            <span class="observability-page__divider-inline" />
            <span>
              异常：<strong class="is-danger">{{ page.issueCount }}</strong>
            </span>
          </span>
        </div>
      </template>


      <!-- 上线值守摘要 -->
      <div class="observability-page__ops-summary">
        <div class="observability-page__ops-status">
          <span
            class="observability-page__ops-dot"
            :class="`observability-page__ops-dot--${page.summaryStatusType}`"
          />
          <div>
            <strong>{{ page.summaryStatusLabel }}</strong>
            <span v-if="page.summaryErrorMessage">{{ page.summaryErrorMessage }}</span>
            <span v-else>上线值守雷达：失败、慢处理和处理中队列</span>
          </div>
        </div>
        <router-link
          v-for="item in page.summaryCards"
          :key="item.label"
          class="observability-page__ops-card"
          :class="`observability-page__ops-card--${item.level}`"
          :to="item.route"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </router-link>
      </div>


      <!-- 紧凑单行筛选工具栏：回写历史 -->
      <div v-if="page.activeTab === 'history'" class="observability-page__toolbar">
        <div class="observability-page__toolbar-left">
          <el-select v-model="page.historyStatusDraft" clearable placeholder="处理结果" style="width: 110px">
            <el-option label="全部结果" value="" />
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
          </el-select>
          <el-select v-model="page.historySourceDraft" clearable placeholder="来源" style="width: 130px">
            <el-option label="全部来源" value="" />
            <el-option label="后台知识配置" value="admin_knowledge" />
            <el-option label="有赞 Webhook" value="youzan_webhook" />
            <el-option label="种子导入" value="seed_knowledge" />
          </el-select>
          <el-select v-model="page.historyEntityTypeDraft" clearable placeholder="实体类型" style="width: 110px">
            <el-option label="全部类型" value="" />
            <el-option label="知识" value="knowledge" />
            <el-option label="商品" value="product" />
          </el-select>
          <el-input
            v-model="page.historyKeywordDraft"
            clearable
            placeholder="搜索标题、实体键或来源引用"
            class="observability-page__search"
            @keyup.enter="page.submitHistoryFilters"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>
        <div class="observability-page__toolbar-right">
          <el-button type="primary" :icon="Search" @click="page.submitHistoryFilters">筛选</el-button>
          <el-button @click="page.historyStatusDraft = props.mode === 'failures' ? 'failed' : ''; page.historySourceDraft = ''; page.historyEntityTypeDraft = ''; page.historyKeywordDraft = ''; page.submitHistoryFilters()">
            重置
          </el-button>
        </div>
      </div>

      <!-- 紧凑单行筛选工具栏：Webhook 审计 -->
      <div v-else class="observability-page__toolbar">
        <div class="observability-page__toolbar-left">
          <el-select v-model="page.webhookStatusDraft" clearable placeholder="处理结果" style="width: 110px">
            <el-option label="全部结果" value="" />
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
            <el-option label="处理中" value="processing" />
          </el-select>
          <el-input
            v-model="page.webhookEventTypeDraft"
            clearable
            placeholder="事件类型，如 ITEM_INFO"
            style="width: 180px"
            @keyup.enter="page.submitWebhookFilters"
          />
          <el-input
            v-model="page.webhookKeywordDraft"
            clearable
            placeholder="搜索 msg_id、业务键或错误信息"
            class="observability-page__search"
            @keyup.enter="page.submitWebhookFilters"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>
        <div class="observability-page__toolbar-right">
          <el-button type="primary" :icon="Search" @click="page.submitWebhookFilters">筛选</el-button>
          <el-button @click="page.webhookStatusDraft = props.mode === 'failures' ? 'failed' : ''; page.webhookEventTypeDraft = ''; page.webhookKeywordDraft = ''; page.submitWebhookFilters()">
            重置
          </el-button>
        </div>
      </div>

      <!-- 错误警告提示 -->
      <el-alert
        v-if="page.errorMessage"
        class="observability-page__error"
        type="error"
        show-icon
        :closable="false"
      >
        <template #title>
          <span>{{ page.errorMessage }}</span>
          <el-button link type="primary" @click="page.retryLoadData" style="margin-left: 8px">重试</el-button>
        </template>
      </el-alert>

      <!-- PC 桌面端表格区 -->
      <div class="observability-page__desktop" ref="tableWrapper">

        <!-- 回写历史表格 -->
        <el-table
          v-if="page.activeTab === 'history'"
          :data="page.historyRows"
          v-loading="page.loading"
          stripe
          border
          :height="tableHeight"
          class="observability-page__table"
        >
          <el-table-column type="index" label="序号" width="60" align="center" />
          <el-table-column prop="title" label="回写对象 / 业务名" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <button class="observability-page__title-btn" type="button" @click="page.openHistoryDetail(row)">
                {{ row.title }}
              </button>
            </template>
          </el-table-column>
          <el-table-column label="变更内容与来源" min-width="380" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="observability-page__change-summary" style="font-weight: 500; margin-bottom: 6px;" v-html="parseChangeSummary(row.details, row.entityType, row.action, row.source)">
              </div>
              <div style="display: flex; gap: 8px; align-items: center; font-size: 12px; color: var(--yx-text-muted);">
                <el-tag size="small" :type="row.source === 'youzan_webhook' ? 'warning' : 'info'" effect="plain">
                  {{ formatSource(row.source) }}
                </el-tag>
                <span v-if="row.webhookEventType" style="color: var(--yx-primary)">触发: {{ formatEventType(row.webhookEventType) }}</span>
                <span>动作: {{ formatAction(row.action) }}（{{ formatEntityType(row.entityType) }}）</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="结果" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.statusType" effect="light" size="small">
                {{ row.statusLabel }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="errorLabel" label="错误日志" width="110" align="center">
            <template #default="{ row }">
              <el-button
                v-if="row.errorLabel && row.errorLabel !== '-'"
                type="danger"
                link
                @click="openErrorDialog(row.errorLabel)"
              >
                查看日志
              </el-button>
              <span v-else class="observability-page__none">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="occurredAtLabel" label="发生时间" width="170" align="center" />
          <el-table-column label="操作" width="80" fixed="right" align="center">
            <template #default="{ row }">
              <el-button link type="primary" @click="page.openHistoryDetail(row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- Webhook 审计表格 -->
        <el-table
          v-else
          :data="page.webhookRows"
          v-loading="page.loading"
          stripe
          border
          :height="tableHeight"
          class="observability-page__table"
        >
          <el-table-column type="index" label="序号" width="60" align="center" />
          <el-table-column prop="eventType" label="推送接口 / 事件类型" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <button class="observability-page__title-btn" type="button" @click="page.openWebhookDetail(row)">
                {{ formatEventType(row.eventType) }}
              </button>
              <div class="observability-page__mono" style="font-size: 11px; margin-top: 2px;">
                {{ row.eventType }}
              </div>
            </template>
          </el-table-column>
          <el-table-column label="核心关联业务 / 干嘛的" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="observability-page__biz-summary">
                {{ parseWebhookSummary(row.details, row.eventType, row.businessType, row.businessKey) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.statusType" effect="light" size="small">
                {{ row.statusLabel }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="processStage" label="处理阶段" width="120" align="center" />
          <el-table-column prop="durationLabel" label="消费耗时" width="100" align="right" />
          <el-table-column prop="errorLabel" label="错误日志" width="110" align="center">
            <template #default="{ row }">
              <el-button
                v-if="row.errorLabel && row.errorLabel !== '-'"
                type="danger"
                link
                @click="openErrorDialog(row.errorLabel)"
              >
                查看日志
              </el-button>
              <span v-else class="observability-page__none">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="receivedAtLabel" label="接收时间" width="170" align="center" />
          <el-table-column label="操作" width="80" fixed="right" align="center">
            <template #default="{ row }">
              <el-button link type="primary" @click="page.openWebhookDetail(row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 移动端卡片列表 -->
      <div class="observability-page__mobile">
        <el-skeleton :rows="4" animated v-if="page.loading" />

        <div v-else-if="page.activeTab === 'history'" class="observability-page__cards">
          <button
            v-for="row in page.historyRows"
            :key="row.id"
            type="button"
            class="observability-page__card-item"
            @click="page.openHistoryDetail(row)"
          >
            <div class="observability-page__card-top">
              <strong>{{ row.title }}</strong>
              <el-tag size="small" :type="row.statusType" effect="light">{{ row.status }}</el-tag>
            </div>
            <div class="observability-page__card-meta">
              <span>
                <strong>内容:</strong> <span style="color: var(--yx-text-main); font-weight: 500;" v-html="parseChangeSummary(row.details, row.entityType, row.action, row.source)"></span>
              </span>
              <span>
                <strong>来源:</strong> {{ formatSource(row.source) }}
                <span v-if="row.webhookEventType" style="color: var(--yx-primary)"> ({{ formatEventType(row.webhookEventType) }})</span>
                | {{ formatAction(row.action) }}
              </span>
              <span><strong>时间:</strong> {{ row.occurredAtLabel }}</span>
            </div>
          </button>
        </div>

        <div v-else class="observability-page__cards">
          <button
            v-for="row in page.webhookRows"
            :key="row.id"
            type="button"
            class="observability-page__card-item"
            @click="page.openWebhookDetail(row)"
          >
            <div class="observability-page__card-top">
              <strong>{{ formatEventType(row.eventType) }}</strong>
              <el-tag size="small" :type="row.statusType" effect="light">{{ row.status }}</el-tag>
            </div>
            <div class="observability-page__card-meta">
              <span><strong>业务:</strong> {{ parseWebhookSummary(row.details, row.eventType, row.businessType, row.businessKey) }}</span>
              <span><strong>阶段:</strong> {{ row.processStage || "-" }}</span>
              <span><strong>时间:</strong> {{ row.receivedAtLabel }}</span>
            </div>
          </button>
        </div>
      </div>

      <!-- 空状态 -->
      <el-empty
        v-if="!page.loading && page.listCount === 0"
        :description="props.mode === 'workspace' ? '当前筛选条件下没有记录。' : '当前没有匹配的失败记录。'"
        style="padding: 40px 0"
      />

      <!-- 分页栏 -->
      <div class="observability-page__pagination">
        <div class="observability-page__page-stats">
          <span>当前页 <strong>{{ page.listCount }}</strong> 条</span>
          <span class="observability-page__divider" />
          <span>总计 <strong>{{ page.total }}</strong> 条</span>
        </div>
        <el-pagination
          background
          layout="prev, pager, next"
          :current-page="page.currentPage"
          :page-size="page.pageSize"
          :total="page.total"
          @current-change="page.changePage"
        />
      </div>
    </el-card>

    <ObservabilityDetailDrawer
      :visible="page.drawerVisible"
      :loading="page.detailLoading"
      :title="page.detailTitle"
      :subtitle="page.detailSubtitle"
      :summary-lines="page.detailSummaryLines"
      :detail-fields="page.detailFields"
      :error-message="page.detailErrorMessage"
      :show-track-btn="false"
      :entity-key="page.detailEntityKey"
      :entity-type="page.detailEntityType"
      @update:visible="updateDrawerVisible"
      @track-history="page.trackEntityHistory"
    />

    <!-- 错误日志详情弹窗 (终端风格) -->
    <el-dialog
      v-model="errorDialogVisible"
      title="错误日志详情"
      width="720px"
      destroy-on-close
      append-to-body
      class="observability-page__error-dialog"
    >
      <div class="observability-page__terminal">
        <div class="observability-page__terminal-header">
          <div class="observability-page__terminal-dots">
            <span class="observability-page__dot red"></span>
            <span class="observability-page__dot yellow"></span>
            <span class="observability-page__dot green"></span>
          </div>
          <span class="observability-page__terminal-title">System Stack Trace & Diagnostic Logs</span>
        </div>
        <div class="observability-page__terminal-body">
          <pre class="observability-page__terminal-pre"><code>{{ activeErrorLog }}</code></pre>
        </div>
      </div>
      <div class="observability-page__error-footer" style="margin-top: 20px; display: flex; justify-content: flex-end; gap: 12px;">
        <el-button @click="copyErrorLog" type="primary" plain>一键复制</el-button>
        <el-button @click="errorDialogVisible = false">关闭</el-button>
      </div>
    </el-dialog>
  </section>
</template>

<style scoped>
/* ── 页面根容器 ── */
.observability-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── 单主卡片：铺满剩余高度 ── */
.observability-page__card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.observability-page__card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

/* ── 卡片头 ── */
.observability-page__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
}

.observability-page__header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
  flex-wrap: wrap;
}

.observability-page__page-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--yx-text);
  white-space: nowrap;
}

/* ── 统计快捷 Tab ── */
.observability-page__stat-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
}

.observability-page__stat-tab {
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

.observability-page__stat-tab:hover {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.observability-page__stat-tab.is-active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.observability-page__card-total {
  font-size: 13px;
  color: var(--yx-text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.observability-page__card-total strong {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: var(--yx-text);
}

.observability-page__card-total strong.is-danger {
  color: var(--el-color-danger);
}

.observability-page__divider-inline {
  display: inline-block;
  width: 1px;
  height: 10px;
  background: var(--el-border-color-lighter);
  margin: 0 8px;
}

/* ── 上线值守摘要 ── */
.observability-page__ops-summary {
  display: grid;
  grid-template-columns: minmax(220px, 1.4fr) repeat(4, minmax(110px, 1fr));
  gap: 10px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background:
    radial-gradient(circle at 12% 10%, rgba(245, 158, 11, 0.12), transparent 24%),
    linear-gradient(135deg, rgba(255, 247, 237, 0.78), rgba(248, 250, 252, 0.92));
  flex-shrink: 0;
}

.observability-page__ops-status,
.observability-page__ops-card {
  min-width: 0;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.82);
}

.observability-page__ops-status {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
}

.observability-page__ops-status div {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.observability-page__ops-status strong {
  font-size: 14px;
  color: var(--yx-text);
}

.observability-page__ops-status span:last-child {
  overflow: hidden;
  color: var(--yx-text-muted);
  font-size: 12px;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.observability-page__ops-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #10b981;
  flex-shrink: 0;
  box-shadow: 0 0 0 5px rgba(16, 185, 129, 0.12);
}

.observability-page__ops-dot--warning {
  background: #f59e0b;
  box-shadow: 0 0 0 5px rgba(245, 158, 11, 0.14);
}

.observability-page__ops-dot--danger {
  background: #ef4444;
  box-shadow: 0 0 0 5px rgba(239, 68, 68, 0.14);
}

.observability-page__ops-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px;
  color: var(--yx-text);
  text-decoration: none;
  transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}

.observability-page__ops-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
}

.observability-page__ops-card span {
  color: var(--yx-text-muted);
  font-size: 12px;
}

.observability-page__ops-card strong {
  font-size: 22px;
  font-variant-numeric: tabular-nums;
}

.observability-page__ops-card--danger {
  border-color: #fecaca;
  background: #fff5f5;
}

.observability-page__ops-card--danger strong {
  color: #ef4444;
}

.observability-page__ops-card--warning {
  border-color: #fed7aa;
  background: #fff7ed;
}

.observability-page__ops-card--warning strong {
  color: #f59e0b;
}

.observability-page__ops-card--info strong {
  color: var(--el-color-primary);
}

/* ── 工具栏：筛选项单行 ── */
.observability-page__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-wrap: wrap;
  flex-shrink: 0;
}

.observability-page__toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.observability-page__search {
  width: 260px;
}

.observability-page__toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ── 桌面端表格区 ── */
.observability-page__desktop {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.observability-page__mobile {
  display: none;
}

/* ── 表格样式 ── */
.observability-page__table {
  flex: 1;
  --el-table-text-color: var(--yx-text);
}

.observability-page__table :deep(.el-table__header th) {
  padding: 10px 0;
  text-align: center;
}

.observability-page__table :deep(.el-table__header th .cell) {
  white-space: nowrap;
}

.observability-page__table :deep(.el-table__row td) {
  padding: 14px 0;
}

.observability-page__table :deep(.el-table__cell) {
  vertical-align: middle;
}

/* ── 单元格样式 ── */
.observability-page__title-btn {
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

.observability-page__title-btn:hover {
  color: var(--el-color-primary-dark-2);
}

.observability-page__mono {
  font-size: 13px;
  color: var(--yx-text-muted);
  font-family: var(--yx-font-mono), monospace;
}

.observability-page__change-summary,
.observability-page__biz-summary {
  font-size: 12px;
  color: var(--yx-text);
}

.observability-page__error {
  margin: 12px 20px 0;
  flex-shrink: 0;
}

/* ── 分页栏 ── */
.observability-page__pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  border-top: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
  flex-shrink: 0;
}

.observability-page__page-stats {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--yx-text-muted);
  white-space: nowrap;
}

.observability-page__page-stats strong {
  font-variant-numeric: tabular-nums;
  color: var(--yx-text);
}

.observability-page__divider {
  display: inline-block;
  width: 1px;
  height: 14px;
  background: var(--el-border-color);
}

/* ── 移动端卡片视图 ── */
@media (max-width: 767px) {
  .observability-page__ops-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding: 12px 16px;
  }

  .observability-page__ops-status {
    grid-column: 1 / -1;
  }

  .observability-page__toolbar {
    padding: 12px 16px;
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }

  .observability-page__toolbar-left {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    width: 100%;
  }

  /* 搜索框独占满宽 */
  .observability-page__toolbar-left > .observability-page__search {
    grid-column: 1 / -1;
    width: 100% !important;
  }

  /* 强制覆盖 select 和 input 默认宽度 */
  .observability-page__toolbar-left .el-select,
  .observability-page__toolbar-left .el-input {
    width: 100% !important;
  }

  .observability-page__toolbar-right {
    width: 100%;
    justify-content: space-between;
  }

  .observability-page__desktop {
    display: none;
  }

  .observability-page__mobile {
    display: block;
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
  }

  .observability-page__cards {
    display: grid;
    gap: 10px;
  }

  .observability-page__card-item {
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

  .observability-page__card-item:active {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }

  .observability-page__card-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    font-size: 14px;
    font-weight: 600;
    color: var(--yx-text);
  }

  .observability-page__card-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 14px;
    font-size: 12px;
    color: var(--yx-text-muted);
  }

  .observability-page__card-meta span {
    width: 100%;
  }

  .observability-page__pagination {
    justify-content: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .observability-page__page-stats {
    display: none;
  }
}

/* ── 错误日志终端弹窗样式 ── */
:deep(.observability-page__error-dialog) {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.25);
  background: var(--yx-bg-card, #ffffff);
  border: 1px solid var(--yx-border, #e4e7ed);
}

:deep(.observability-page__error-dialog .el-dialog__header) {
  margin-right: 0;
  padding: 20px 24px 10px;
}

:deep(.observability-page__error-dialog .el-dialog__body) {
  padding: 0 24px 10px;
}

.observability-page__terminal {
  background: #1e1e24;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #2d2d36;
  box-shadow: inset 0 0 10px rgba(0,0,0,0.5);
}

.observability-page__terminal-header {
  background: #18181c;
  padding: 10px 16px;
  display: flex;
  align-items: center;
  border-bottom: 1px solid #25252b;
}

.observability-page__terminal-dots {
  display: flex;
  gap: 6px;
  margin-right: 16px;
}

.observability-page__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}

.observability-page__dot.red { background: #ff5f56; }
.observability-page__dot.yellow { background: #ffbd2e; }
.observability-page__dot.green { background: #27c93f; }

.observability-page__terminal-title {
  color: #8e8e93;
  font-size: 12px;
  font-family: monospace;
  user-select: none;
}

.observability-page__terminal-body {
  padding: 16px;
  max-height: 400px;
  overflow-y: auto;
}

.observability-page__terminal-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: Consolas, Monaco, 'Andale Mono', 'Ubuntu Mono', monospace;
  font-size: 13px;
  line-height: 1.6;
}

.observability-page__terminal-pre code {
  color: #ff79c6; /* 亮粉色展示，让报错信息非常醒目 */
}

.observability-page__error-footer {
  padding-bottom: 10px;
}
</style>
