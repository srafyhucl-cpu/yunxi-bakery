<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";

import { printJobsService } from "@/services/printJobs";
import type {
  PrintJobItem,
  PrintJobStatus,
  PrintTicketType,
} from "@/types/printJob";

type TagType = "primary" | "success" | "info" | "warning" | "danger";

interface StatusMeta {
  text: string;
  type: TagType;
}

interface StatusOption {
  label: string;
  value: PrintJobStatus | "";
}

const STATUS_OPTIONS: StatusOption[] = [
  { label: "全部", value: "" },
  { label: "待打印", value: "PENDING" },
  { label: "失败", value: "FAILED" },
  { label: "已提交", value: "SUBMITTED" },
  { label: "已 Mock", value: "MOCKED" },
  { label: "已出纸", value: "PRINTED" },
  { label: "处理中", value: "CLAIMED" },
  { label: "已取消", value: "CANCELLED" },
];

const STATUS_META: Record<PrintJobStatus, StatusMeta> = {
  PENDING: { text: "待打印", type: "warning" },
  CLAIMED: { text: "处理中", type: "primary" },
  SUBMITTED: { text: "已提交", type: "primary" },
  MOCKED: { text: "已 Mock", type: "warning" },
  PRINTED: { text: "已出纸", type: "success" },
  FAILED: { text: "失败", type: "danger" },
  CANCELLED: { text: "已取消", type: "info" },
};

const TICKET_TYPE_LABELS: Record<PrintTicketType, string> = {
  CAKE_KITCHEN: "裱花间制作联",
  DAILY_FRONT: "日常现烤联",
};

const loading = ref(false);
const processing = ref(false);
const errorMessage = ref("");
const statusFilter = ref<PrintJobStatus | "">("");
const items = ref<PrintJobItem[]>([]);
const busyKey = ref("");

let loadSequence = 0;

const pendingCount = computed(
  () => items.value.filter((item) => item.status === "PENDING").length,
);
const failedCount = computed(
  () => items.value.filter((item) => item.status === "FAILED").length,
);
const acceptedCount = computed(
  () =>
    items.value.filter(
      (item) => item.status === "SUBMITTED" || item.status === "MOCKED",
    ).length,
);

function readErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (
      error as { response?: { data?: { detail?: unknown; message?: unknown } } }
    ).response;
    const detail = response?.data?.detail ?? response?.data?.message;
    if (typeof detail === "string" && detail) {
      return detail;
    }
  }
  return fallback;
}

function statusMeta(status: string): StatusMeta {
  return (
    STATUS_META[status as PrintJobStatus] || { text: status || "未知", type: "info" }
  );
}

function ticketTypeLabel(ticketType: string): string {
  return TICKET_TYPE_LABELS[ticketType as PrintTicketType] || ticketType || "未知小票";
}

function isBusy(action: string, jobId: string): boolean {
  return busyKey.value === `${action}:${jobId}`;
}

/** 仅待打印与失败作业可重新提交打印。 */
function canRetry(row: PrintJobItem): boolean {
  return row.status === "PENDING" || row.status === "FAILED";
}

/** 已受理或模拟受理的作业需要人工确认真实出纸。 */
function canMarkPrinted(row: PrintJobItem): boolean {
  return row.status === "SUBMITTED" || row.status === "MOCKED";
}

/** 已取消作业只读；其余状态均可补打新建作业。 */
function canReprint(row: PrintJobItem): boolean {
  return row.status !== "CANCELLED";
}

async function loadJobs(): Promise<void> {
  const sequence = ++loadSequence;
  loading.value = true;
  errorMessage.value = "";
  try {
    const payload = await printJobsService.list(statusFilter.value);
    if (sequence !== loadSequence) {
      return;
    }
    items.value = payload.items;
  } catch (error) {
    if (sequence !== loadSequence) {
      return;
    }
    errorMessage.value = readErrorMessage(error, "打印队列加载失败");
    ElMessage.error(errorMessage.value);
  } finally {
    if (sequence === loadSequence) {
      loading.value = false;
    }
  }
}

async function processPending(): Promise<void> {
  processing.value = true;
  try {
    const summary = await printJobsService.processPending();
    const message = `已处理：Mock ${summary.mocked} · 已提交 ${summary.submitted} · 失败 ${summary.failed}`;
    if (summary.failed > 0) {
      ElMessage.warning(message);
    } else {
      ElMessage.success(message);
    }
    await loadJobs();
  } catch (error) {
    ElMessage.error(readErrorMessage(error, "处理待打印作业失败"));
  } finally {
    processing.value = false;
  }
}

async function retryJob(row: PrintJobItem): Promise<void> {
  busyKey.value = `retry:${row.id}`;
  try {
    const result = await printJobsService.retry(row.id);
    if (result.success) {
      ElMessage.success(
        result.status === "MOCKED" ? "重试完成：已模拟出纸" : "重试完成：已提交打印商",
      );
    } else {
      ElMessage.error(result.error || "重试失败");
    }
    await loadJobs();
  } catch (error) {
    ElMessage.error(readErrorMessage(error, "重试打印失败"));
  } finally {
    busyKey.value = "";
  }
}

async function markPrintedJob(row: PrintJobItem): Promise<void> {
  busyKey.value = `mark:${row.id}`;
  try {
    await printJobsService.markPrinted(row.id);
    ElMessage.success("已确认出纸，作业标记为已打印");
    await loadJobs();
  } catch (error) {
    ElMessage.error(readErrorMessage(error, "确认出纸失败"));
  } finally {
    busyKey.value = "";
  }
}

async function reprintJob(row: PrintJobItem): Promise<void> {
  busyKey.value = `reprint:${row.id}`;
  try {
    await printJobsService.reprint(row.orderId, row.ticketType);
    ElMessage.success("补打作业已创建，可在待打印中查看");
    await loadJobs();
  } catch (error) {
    ElMessage.error(readErrorMessage(error, "补打失败"));
  } finally {
    busyKey.value = "";
  }
}

onMounted(() => {
  void loadJobs();
});
</script>

<template>
  <section class="print-jobs-page" data-testid="print-jobs-page">
    <el-card shadow="never">
      <template #header>
        <div class="print-jobs-page__header">
          <div>
            <strong>打印队列</strong>
            <p>
              按订单查看小票打印作业状态。确认出纸后视为已打印；补打会复制原小票内容新建一条待打印作业。
            </p>
          </div>
          <div class="print-jobs-page__actions">
            <el-button
              :icon="Refresh"
              :loading="loading"
              data-testid="print-jobs-refresh"
              @click="loadJobs"
            >
              刷新
            </el-button>
            <el-button
              type="primary"
              :loading="processing"
              data-testid="print-jobs-process-pending"
              @click="processPending"
            >
              处理待打印
            </el-button>
          </div>
        </div>
      </template>

      <div class="print-jobs-page__toolbar">
        <el-select
          v-model="statusFilter"
          class="print-jobs-page__filter"
          data-testid="print-jobs-status-filter"
          @change="loadJobs"
        >
          <el-option
            v-for="option in STATUS_OPTIONS"
            :key="option.value || 'all'"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <div class="print-jobs-page__stats" data-testid="print-jobs-stats">
          <span class="print-jobs-page__stat">
            待打印 <b>{{ pendingCount }}</b>
          </span>
          <span class="print-jobs-page__stat print-jobs-page__stat--danger">
            失败 <b>{{ failedCount }}</b>
          </span>
          <span class="print-jobs-page__stat print-jobs-page__stat--accepted">
            已提交/已 Mock <b>{{ acceptedCount }}</b>
          </span>
          <span class="print-jobs-page__stat print-jobs-page__stat--muted">
            当前列表 {{ items.length }} 条
          </span>
        </div>
      </div>

      <el-alert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        show-icon
        :closable="false"
        class="print-jobs-page__error"
        data-testid="print-jobs-error"
      />

      <div class="print-jobs-page__table-wrap">
        <el-table
          :data="items"
          v-loading="loading"
          stripe
          class="print-jobs-page__table"
          data-testid="print-jobs-table"
        >
          <el-table-column label="订单号" min-width="170" show-overflow-tooltip>
            <template #default="{ row }">{{ row.orderId || "-" }}</template>
          </el-table-column>
          <el-table-column label="小票类型" width="130">
            <template #default="{ row }">{{ ticketTypeLabel(row.ticketType) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag
                :type="statusMeta(row.status).type"
                size="small"
                effect="light"
                :data-testid="`print-jobs-status-${row.id}`"
              >
                {{ statusMeta(row.status).text }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="尝试次数" width="90" align="center">
            <template #default="{ row }">{{ row.attempts }}</template>
          </el-table-column>
          <el-table-column label="打印商" width="110" show-overflow-tooltip>
            <template #default="{ row }">{{ row.provider || "-" }}</template>
          </el-table-column>
          <el-table-column label="内容预览" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ row.contentPreview || "-" }}</template>
          </el-table-column>
          <el-table-column label="错误" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.lastError" class="print-jobs-page__error-text">
                {{ row.lastError }}
              </span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">{{ row.updatedAt || "-" }}</template>
          </el-table-column>
          <el-table-column label="操作" width="230" fixed="right" align="center">
            <template #default="{ row }">
              <div v-if="row.status === 'CANCELLED'" class="print-jobs-page__readonly">
                只读
              </div>
              <div v-else class="print-jobs-page__row-actions">
                <el-button
                  v-if="canRetry(row)"
                  type="primary"
                  size="small"
                  plain
                  :loading="isBusy('retry', row.id)"
                  :disabled="!!busyKey && !isBusy('retry', row.id)"
                  :data-testid="`print-jobs-retry-${row.id}`"
                  @click="retryJob(row)"
                >
                  重试
                </el-button>
                <el-tooltip
                  v-if="canMarkPrinted(row)"
                  content="确认出纸后视为已打印"
                  placement="top"
                >
                  <el-button
                    type="success"
                    size="small"
                    plain
                    :loading="isBusy('mark', row.id)"
                    :disabled="!!busyKey && !isBusy('mark', row.id)"
                    :data-testid="`print-jobs-mark-printed-${row.id}`"
                    @click="markPrintedJob(row)"
                  >
                    确认出纸
                  </el-button>
                </el-tooltip>
                <el-button
                  v-if="canReprint(row)"
                  size="small"
                  :loading="isBusy('reprint', row.id)"
                  :disabled="!!busyKey && !isBusy('reprint', row.id)"
                  :data-testid="`print-jobs-reprint-${row.id}`"
                  @click="reprintJob(row)"
                >
                  补打
                </el-button>
              </div>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty
              :description="statusFilter ? '当前筛选条件下暂无打印作业' : '暂无打印作业'"
              data-testid="print-jobs-empty"
            />
          </template>
        </el-table>
      </div>
    </el-card>
  </section>
</template>

<style scoped>
.print-jobs-page {
  display: grid;
  gap: 16px;
}

.print-jobs-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.print-jobs-page__header p {
  margin: 6px 0 0;
  color: var(--yx-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.print-jobs-page__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.print-jobs-page__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.print-jobs-page__filter {
  width: 180px;
}

.print-jobs-page__stats {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--yx-text-muted);
}

.print-jobs-page__stat {
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--yx-bg);
}

.print-jobs-page__stat b {
  color: var(--el-text-color-primary);
  font-size: 13px;
}

.print-jobs-page__stat--danger b {
  color: var(--el-color-danger);
}

.print-jobs-page__stat--accepted b {
  color: var(--el-color-primary);
}

.print-jobs-page__stat--muted {
  background: transparent;
}

.print-jobs-page__error {
  margin-bottom: 12px;
}

.print-jobs-page__table-wrap {
  width: 100%;
  overflow-x: auto;
}

.print-jobs-page__table {
  min-width: 1180px;
}

.print-jobs-page__error-text {
  color: var(--el-color-danger);
}

.print-jobs-page__row-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex-wrap: wrap;
}

.print-jobs-page__readonly {
  color: var(--yx-text-muted);
  font-size: 12px;
}

@media (max-width: 767px) {
  .print-jobs-page__header {
    flex-direction: column;
  }

  .print-jobs-page__toolbar {
    align-items: stretch;
  }

  .print-jobs-page__filter {
    width: 100%;
  }
}
</style>
