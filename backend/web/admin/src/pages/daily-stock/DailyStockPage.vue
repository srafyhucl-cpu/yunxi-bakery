<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Calendar, Refresh } from "@element-plus/icons-vue";

import { dailyStockService } from "@/services/dailyStock";
import type { DailyStockItem } from "@/types/dailyStock";

interface StatusBadge {
  text: string;
  type: "info" | "success" | "warning";
}

const loading = ref(false);
const errorMessage = ref("");
const stockDate = ref(todayString());
const items = ref<DailyStockItem[]>([]);
const savingProductId = ref("");
const drafts = reactive<Record<string, number | undefined>>({});
let loadSequence = 0;

const configuredCount = computed(
  () => items.value.filter((item) => item.configured).length,
);
const soldOutCount = computed(
  () => items.value.filter((item) => item.configured && item.available_qty <= 0).length,
);

function todayString(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const valueOf = (type: string) => parts.find((part) => part.type === type)?.value || "";
  return `${valueOf("year")}-${valueOf("month")}-${valueOf("day")}`;
}

function syncDrafts(): void {
  for (const key of Object.keys(drafts)) {
    delete drafts[key];
  }
  for (const item of items.value) {
    drafts[item.product_id] = item.total_qty;
  }
}

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

function statusOf(item: DailyStockItem): StatusBadge {
  if (!item.configured) {
    return { text: "未配置", type: "info" };
  }
  if (item.available_qty <= 0) {
    return { text: "已售罄", type: "warning" };
  }
  return { text: "已配置", type: "success" };
}

async function loadItems(): Promise<void> {
  const sequence = ++loadSequence;
  loading.value = true;
  errorMessage.value = "";
  try {
    const payload = await dailyStockService.list(stockDate.value);
    if (sequence !== loadSequence) {
      return;
    }
    items.value = payload.items;
    syncDrafts();
  } catch (error) {
    if (sequence !== loadSequence) {
      return;
    }
    errorMessage.value = readErrorMessage(error, "每日库存加载失败");
    ElMessage.error(errorMessage.value);
  } finally {
    if (sequence === loadSequence) {
      loading.value = false;
    }
  }
}

async function saveItem(row: DailyStockItem): Promise<void> {
  const draft = drafts[row.product_id];
  if (typeof draft !== "number" || !Number.isInteger(draft) || draft < 0) {
    ElMessage.warning("请输入有效的非负整数总量");
    return;
  }
  const totalQty = draft;
  if (totalQty < row.reserved_qty) {
    ElMessage.warning(`总量不能低于已预占数量 ${row.reserved_qty}`);
    return;
  }
  savingProductId.value = row.product_id;
  try {
    const updated = await dailyStockService.setTotal(
      row.product_id,
      stockDate.value,
      totalQty,
    );
    items.value = items.value.map((item) =>
      item.product_id === updated.product_id ? updated : item,
    );
    drafts[updated.product_id] = updated.total_qty;
    ElMessage.success("每日库存已保存");
  } catch (error) {
    ElMessage.error(readErrorMessage(error, "保存每日库存失败"));
  } finally {
    savingProductId.value = "";
  }
}

onMounted(() => {
  void loadItems();
});
</script>

<template>
  <section class="daily-stock-page" data-testid="daily-stock-page">
    <el-card shadow="never">
      <template #header>
        <div class="daily-stock-page__header">
          <div>
            <strong>每日库存</strong>
            <p>
              按北京时间日期维护现烤商品当日可售总量；保存只更新每日库存，不影响有赞库存。
              未配置的商品总量为 0，首次进入可直接录入。
            </p>
          </div>
          <div class="daily-stock-page__actions">
            <span class="daily-stock-page__stats" data-testid="daily-stock-stats">
              共 {{ items.length }} 款 · 已配置 {{ configuredCount }} · 售罄 {{ soldOutCount }}
            </span>
            <el-button
              :icon="Refresh"
              :loading="loading"
              data-testid="daily-stock-refresh"
              @click="loadItems"
            >
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <div class="daily-stock-page__toolbar">
        <el-date-picker
          v-model="stockDate"
          type="date"
          value-format="YYYY-MM-DD"
          format="YYYY-MM-DD"
          placeholder="选择日期"
          :clearable="false"
          :prefix-icon="Calendar"
          class="daily-stock-page__date"
          data-testid="daily-stock-date-picker"
          @change="loadItems"
        />
      </div>

      <el-alert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        show-icon
        :closable="false"
        class="daily-stock-page__error"
        data-testid="daily-stock-error"
      />

      <div class="daily-stock-page__table-wrap">
        <el-table
          :data="items"
          v-loading="loading"
          stripe
          class="daily-stock-page__table"
          data-testid="daily-stock-table"
        >
          <el-table-column label="商品名" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="daily-stock-page__product">
                <span>{{ row.title }}</span>
                <el-tag v-if="row.is_active !== 1" type="info" size="small" effect="plain">
                  已下架
                </el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="有赞库存" width="100" align="center">
            <template #default="{ row }">{{ row.youzan_stock }}</template>
          </el-table-column>
          <el-table-column label="今日总量" width="180" align="center">
            <template #default="{ row }">
              <el-input-number
                v-model="drafts[row.product_id]"
                :min="0"
                :step="1"
                :precision="0"
                size="small"
                controls-position="right"
                class="daily-stock-page__qty"
                :data-testid="`daily-stock-total-input-${row.product_id}`"
              />
            </template>
          </el-table-column>
          <el-table-column label="已预占" width="100" align="center">
            <template #default="{ row }">{{ row.reserved_qty }}</template>
          </el-table-column>
          <el-table-column label="可售" width="100" align="center">
            <template #default="{ row }">
              <span :class="{ 'daily-stock-page__sold-out': row.configured && row.available_qty <= 0 }">
                {{ row.available_qty }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag
                :type="statusOf(row).type"
                size="small"
                effect="light"
                :data-testid="`daily-stock-status-${row.product_id}`"
              >
                {{ statusOf(row).text }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110" fixed="right" align="center">
            <template #default="{ row }">
              <el-button
                type="primary"
                size="small"
                :loading="savingProductId === row.product_id"
                :data-testid="`daily-stock-save-${row.product_id}`"
                @click="saveItem(row)"
              >
                保存
              </el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty
              description="该日期暂无在售商品"
              data-testid="daily-stock-empty"
            />
          </template>
        </el-table>
      </div>
    </el-card>
  </section>
</template>

<style scoped>
.daily-stock-page {
  display: grid;
  gap: 16px;
}

.daily-stock-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.daily-stock-page__header p {
  margin: 6px 0 0;
  color: var(--yx-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.daily-stock-page__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.daily-stock-page__stats {
  color: var(--yx-text-muted);
  font-size: 12px;
}

.daily-stock-page__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.daily-stock-page__date {
  width: 180px;
}

.daily-stock-page__error {
  margin-bottom: 12px;
}

.daily-stock-page__table-wrap {
  width: 100%;
  overflow-x: auto;
}

.daily-stock-page__table {
  min-width: 780px;
}

.daily-stock-page__product {
  display: flex;
  align-items: center;
  gap: 8px;
}

.daily-stock-page__qty {
  width: 130px;
}

.daily-stock-page__sold-out {
  color: var(--el-color-warning);
  font-weight: 600;
}

@media (max-width: 767px) {
  .daily-stock-page__header {
    flex-direction: column;
  }

  .daily-stock-page__date {
    width: 100%;
  }
}
</style>
