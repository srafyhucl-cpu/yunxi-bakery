<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

import { knowledgeRetrievalReportService } from "@/services/knowledgeRetrievalReport";
import type {
  KnowledgeRetrievalBreakdown,
  KnowledgeRetrievalLog,
  KnowledgeRetrievalReport,
} from "@/types/knowledgeRetrievalReport";

const REPORT_LIMIT_OPTIONS = [50, 100, 200, 500];
const PERCENT_MULTIPLIER = 100;

const loading = ref(false);
const limit = ref(100);
const report = ref<KnowledgeRetrievalReport | null>(null);

const summary = computed(() => report.value?.summary);
const recentLogs = computed<KnowledgeRetrievalLog[]>(() => report.value?.recentLogs || []);

const breakdownSections = computed(() => {
  const breakdown = report.value?.breakdown;
  if (!breakdown) {
    return [];
  }
  return [
    { title: "机器人", items: toBreakdownRows(breakdown.byBotType) },
    { title: "可见范围", items: toBreakdownRows(breakdown.byAudience) },
    { title: "检索模式", items: toBreakdownRows(breakdown.byRetrievalMode) },
    { title: "兜底原因", items: toBreakdownRows(breakdown.byFallbackReason) },
  ];
});

function toBreakdownRows(source: KnowledgeRetrievalBreakdown[keyof KnowledgeRetrievalBreakdown]) {
  return Object.entries(source).map(([name, count]) => ({ name, count }));
}

function formatRate(value: number): string {
  return `${(value * PERCENT_MULTIPLIER).toFixed(1)}%`;
}

function formatText(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (Array.isArray(value)) {
    return value.length ? value.map(String).join("、") : "-";
  }
  return String(value);
}

async function loadReport() {
  loading.value = true;
  try {
    report.value = await knowledgeRetrievalReportService.getSummary(limit.value);
  } catch (error) {
    ElMessage.error("知识检索报表加载失败");
    throw error;
  } finally {
    loading.value = false;
  }
}

onMounted(loadReport);
</script>

<template>
  <section class="knowledge-report-page">
    <el-card shadow="never" class="knowledge-report-page__card">
      <template #header>
        <div class="knowledge-report-page__header">
          <div>
            <span class="knowledge-report-page__title">知识检索报表</span>
            <span class="knowledge-report-page__meta">
              生成时间 {{ report?.metadata.generatedAt || "-" }}
            </span>
          </div>
          <div class="knowledge-report-page__actions">
            <el-select v-model="limit" class="knowledge-report-page__limit" @change="loadReport">
              <el-option
                v-for="item in REPORT_LIMIT_OPTIONS"
                :key="item"
                :label="`${item} 条`"
                :value="item"
              />
            </el-select>
            <el-button :icon="Refresh" :loading="loading" @click="loadReport">
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <div v-loading="loading" class="knowledge-report-page__body">
        <div class="knowledge-report-page__metrics">
          <div class="knowledge-report-page__metric">
            <span>加载日志</span>
            <strong>{{ summary?.total ?? 0 }}</strong>
          </div>
          <div class="knowledge-report-page__metric">
            <span>命中次数</span>
            <strong>{{ summary?.hitCount ?? 0 }}</strong>
          </div>
          <div class="knowledge-report-page__metric knowledge-report-page__metric--warning">
            <span>未命中次数</span>
            <strong>{{ summary?.noMatchCount ?? 0 }}</strong>
          </div>
          <div class="knowledge-report-page__metric knowledge-report-page__metric--danger">
            <span>未命中率</span>
            <strong>{{ formatRate(summary?.noMatchRate ?? 0) }}</strong>
          </div>
        </div>

        <div class="knowledge-report-page__grid">
          <section class="knowledge-report-page__panel">
            <div class="knowledge-report-page__panel-title">按天趋势</div>
            <el-table
              :data="report?.trend.byDate || []"
              class="knowledge-report-page__table"
              size="small"
              stripe
            >
              <el-table-column prop="date" label="日期" min-width="110" />
              <el-table-column prop="total" label="总数" width="80" />
              <el-table-column prop="hitCount" label="命中" width="80" />
              <el-table-column prop="noMatchCount" label="未命中" width="90" />
              <el-table-column label="未命中率" width="100">
                <template #default="{ row }">
                  {{ formatRate(row.noMatchRate) }}
                </template>
              </el-table-column>
            </el-table>
          </section>

          <section class="knowledge-report-page__panel">
            <div class="knowledge-report-page__panel-title">高频未命中</div>
            <el-table
              :data="report?.topNoMatchQueries || []"
              class="knowledge-report-page__table"
              size="small"
              stripe
            >
              <el-table-column prop="query" label="问题" min-width="180" show-overflow-tooltip />
              <el-table-column prop="count" label="次数" width="80" />
            </el-table>
          </section>
        </div>

        <div class="knowledge-report-page__breakdown">
          <section
            v-for="section in breakdownSections"
            :key="section.title"
            class="knowledge-report-page__breakdown-section"
          >
            <div class="knowledge-report-page__panel-title">{{ section.title }}</div>
            <div v-if="section.items.length" class="knowledge-report-page__chips">
              <span
                v-for="item in section.items"
                :key="`${section.title}-${item.name}`"
                class="knowledge-report-page__chip"
              >
                {{ item.name }} <strong>{{ item.count }}</strong>
              </span>
            </div>
            <span v-else class="knowledge-report-page__empty">暂无数据</span>
          </section>
        </div>

        <section class="knowledge-report-page__panel">
          <div class="knowledge-report-page__panel-title">最近检索日志</div>
          <el-table :data="recentLogs" class="knowledge-report-page__table" stripe>
            <el-table-column prop="createdAt" label="时间" min-width="150" />
            <el-table-column prop="botType" label="机器人" width="100" />
            <el-table-column prop="audience" label="范围" width="100" />
            <el-table-column prop="query" label="问题" min-width="220" show-overflow-tooltip />
            <el-table-column prop="retrievalMode" label="模式" width="130" />
            <el-table-column prop="resultCount" label="结果" width="80" />
            <el-table-column label="命中标题" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                {{ formatText(row.matchedTitles) }}
              </template>
            </el-table-column>
            <el-table-column label="兜底" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tag v-if="row.fallbackReason" type="warning" effect="plain">
                  {{ row.fallbackReason }}
                </el-tag>
                <span v-else class="knowledge-report-page__empty">-</span>
              </template>
            </el-table-column>
          </el-table>
        </section>
      </div>
    </el-card>
  </section>
</template>

<style scoped>
.knowledge-report-page {
  min-height: 100%;
  background: #f6f7fb;
  padding: 24px;
}

.knowledge-report-page__card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.knowledge-report-page__card :deep(.el-card__body) {
  padding: 20px;
}

.knowledge-report-page__header,
.knowledge-report-page__actions {
  display: flex;
  align-items: center;
}

.knowledge-report-page__header {
  justify-content: space-between;
  gap: 16px;
}

.knowledge-report-page__actions {
  gap: 10px;
}

.knowledge-report-page__title {
  display: block;
  color: #111827;
  font-size: 18px;
  font-weight: 700;
}

.knowledge-report-page__meta {
  display: block;
  margin-top: 6px;
  color: #6b7280;
  font-size: 12px;
}

.knowledge-report-page__limit {
  width: 108px;
}

.knowledge-report-page__body {
  min-height: 360px;
}

.knowledge-report-page__metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.knowledge-report-page__metric,
.knowledge-report-page__panel,
.knowledge-report-page__breakdown-section {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #ffffff;
}

.knowledge-report-page__metric {
  padding: 16px;
}

.knowledge-report-page__metric span {
  display: block;
  color: #6b7280;
  font-size: 13px;
}

.knowledge-report-page__metric strong {
  display: block;
  margin-top: 8px;
  color: #111827;
  font-size: 24px;
  font-weight: 700;
}

.knowledge-report-page__metric--warning strong {
  color: #b45309;
}

.knowledge-report-page__metric--danger strong {
  color: #b91c1c;
}

.knowledge-report-page__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  margin-top: 16px;
}

.knowledge-report-page__panel {
  padding: 16px;
}

.knowledge-report-page__panel-title {
  margin-bottom: 12px;
  color: #111827;
  font-size: 15px;
  font-weight: 700;
}

.knowledge-report-page__table {
  width: 100%;
}

.knowledge-report-page__table :deep(.el-table__header th) {
  background: #f9fafb;
  color: #374151;
  font-size: 12px;
}

.knowledge-report-page__breakdown {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0;
}

.knowledge-report-page__breakdown-section {
  padding: 14px;
}

.knowledge-report-page__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.knowledge-report-page__chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  border-radius: 6px;
  background: #f3f4f6;
  color: #374151;
  font-size: 12px;
  line-height: 1;
  padding: 7px 9px;
}

.knowledge-report-page__chip strong {
  color: #111827;
}

.knowledge-report-page__empty {
  color: #9ca3af;
}

@media (max-width: 960px) {
  .knowledge-report-page {
    padding: 16px;
  }

  .knowledge-report-page__header {
    align-items: flex-start;
    flex-direction: column;
  }

  .knowledge-report-page__metrics,
  .knowledge-report-page__grid,
  .knowledge-report-page__breakdown {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .knowledge-report-page {
    padding: 12px;
  }

  .knowledge-report-page__actions {
    width: 100%;
  }

  .knowledge-report-page__limit {
    flex: 1;
    width: auto;
  }

  .knowledge-report-page__card :deep(.el-card__body) {
    padding: 14px;
  }
}
</style>
