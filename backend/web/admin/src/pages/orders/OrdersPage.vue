<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { Refresh, Search } from "@element-plus/icons-vue";
import { useRoute } from "vue-router";

import {
  ORDER_BOARD_FILTERS,
  ORDER_STATUS_ACTIONS,
  ORDER_STATUS_OPTIONS,
  orderStatusLabel,
  orderStatusTagType,
  type OrderBoardFilterKey,
} from "@/constants/orderStatus";
import { paymentStatusLabel, paymentStatusTagType } from "@/constants/orderPayment";
import { ordersService } from "@/services/orders";
import type { OrderListItem, OrderStatus, OrderSummaryCard } from "@/types/order";

const route = useRoute();
const loading = ref(false);
const orders = ref<OrderListItem[]>([]);
const keyword = ref(String(route.query.keyword ?? ""));
const status = ref(String(route.query.status ?? ""));
const currentPage = ref(1);
const total = ref(0);
const pageSize = ref(30);
const selectedOrder = ref<OrderListItem | null>(null);
const detailVisible = ref(false);
const actionLoadingKey = ref("");
const activeBoardFilter = ref<OrderBoardFilterKey>("all");
const summaryCards = ref<OrderSummaryCard[]>([]);
const summaryTotalCount = ref(0);
const summaryTotalFen = ref(0);

const totalAmountText = computed(() => {
  const totalFen = orders.value.reduce((sum, order) => sum + order.totalFen, 0);
  return `¥${(totalFen / 100).toFixed(2)}`;
});

const boardCards = computed(() =>
  ORDER_BOARD_FILTERS.map((filter) => {
    const summaryCard = summaryCards.value.find((card) => card.key === filter.key);
    return {
      ...filter,
      count: summaryCard?.count ?? 0,
      amountText: formatFen(summaryCard?.totalFen ?? 0),
      active: filter.key === activeBoardFilter.value,
    };
  }),
);

const selectedOrderActions = computed(() =>
  selectedOrder.value ? ORDER_STATUS_ACTIONS[selectedOrder.value.status] : [],
);
const selectedOrderCanExpireUnpaid = computed(
  () => selectedOrder.value?.paymentStatus === "unpaid" && selectedOrder.value?.status !== "cancelled",
);

const ORDER_TIMELINE_LABELS: Record<string, string> = {
  pending: "提交订单",
  confirmed: "门店确认",
  making: "制作中",
  delivering: "配送/待取",
  done: "已完成",
  cancelled: "已取消",
};

function formatFen(value: number): string {
  return `¥${(value / 100).toFixed(2)}`;
}

function formatTime(value: string): string {
  return value ? value.replace("T", " ").slice(0, 19) : "未记录";
}

function timelineLabel(status: string): string {
  return ORDER_TIMELINE_LABELS[status] ?? status;
}

async function loadOrders(page = currentPage.value): Promise<void> {
  loading.value = true;
  try {
    const payload = await ordersService.listOrders(
      page,
      keyword.value,
      status.value,
      activeBoardFilter.value,
    );
    orders.value = payload.items;
    total.value = payload.total;
    currentPage.value = payload.page;
    pageSize.value = payload.pageSize;
  } finally {
    loading.value = false;
  }
}

async function loadSummary(): Promise<void> {
  const payload = await ordersService.getSummary(keyword.value);
  summaryCards.value = payload.cards;
  summaryTotalCount.value = payload.totalCount;
  summaryTotalFen.value = payload.totalFen;
}

function submitSearch(): void {
  if (status.value) {
    activeBoardFilter.value = "all";
  }
  void loadSummary();
  void loadOrders(1);
}

function resetFilters(): void {
  keyword.value = "";
  status.value = "";
  activeBoardFilter.value = "all";
  void loadSummary();
  void loadOrders(1);
}

function selectBoardFilter(filterKey: OrderBoardFilterKey): void {
  activeBoardFilter.value = filterKey;
  status.value = "";
  void loadOrders(1);
}

async function openDetail(order: OrderListItem): Promise<void> {
  detailVisible.value = true;
  selectedOrder.value = order;
  try {
    selectedOrder.value = await ordersService.getOrder(order.id);
  } catch {
    ElMessage.error("订单详情加载失败");
  }
}

async function updateStatus(order: OrderListItem, nextStatus: OrderStatus): Promise<void> {
  const loadingKey = `${order.id}:${nextStatus}`;
  actionLoadingKey.value = loadingKey;
  try {
    const updated = await ordersService.updateStatus(order.id, nextStatus);
    orders.value = orders.value.map((item) => (item.id === updated.id ? updated : item));
    if (selectedOrder.value?.id === updated.id) {
      selectedOrder.value = updated;
    }
    await loadSummary();
    ElMessage.success(`订单已更新为${orderStatusLabel(updated.status)}`);
  } catch {
    ElMessage.error("订单状态更新失败");
  } finally {
    actionLoadingKey.value = "";
  }
}

async function expireUnpaid(order: OrderListItem): Promise<void> {
  const loadingKey = `${order.id}:expire-unpaid`;
  actionLoadingKey.value = loadingKey;
  try {
    const updated = await ordersService.expireUnpaid(order.id);
    orders.value = orders.value.map((item) => (item.id === updated.id ? updated : item));
    if (selectedOrder.value?.id === updated.id) {
      selectedOrder.value = updated;
    }
    await loadSummary();
    ElMessage.success("未支付订单已关闭");
  } catch {
    ElMessage.error("关闭未支付订单失败");
  } finally {
    actionLoadingKey.value = "";
  }
}

async function expireTimeoutUnpaid(): Promise<void> {
  const loadingKey = "expire-timeout-unpaid";
  actionLoadingKey.value = loadingKey;
  try {
    const result = await ordersService.expireTimeoutUnpaid();
    ElMessage.success(`已关闭 ${result.expiredCount} 笔超时未支付订单`);
    await loadSummary();
    await loadOrders();
  } catch {
    ElMessage.error("扫描超时未支付订单失败");
  } finally {
    actionLoadingKey.value = "";
  }
}

onMounted(() => {
  void loadSummary();
  void loadOrders();
});
</script>

<template>
  <section class="orders-page" data-testid="orders-page">
    <el-card shadow="never" class="orders-page__card">
      <template #header>
        <div class="orders-page__header">
          <div>
            <span class="orders-page__title">订单管理</span>
            <span class="orders-page__subtitle">小程序订单草稿与履约状态</span>
          </div>
          <div class="orders-page__stats">
            <span>当前视图 {{ orders.length }} 单</span>
            <span>金额 {{ totalAmountText }}</span>
            <span>全量 {{ summaryTotalCount }} 单 / {{ formatFen(summaryTotalFen) }}</span>
          </div>
        </div>
      </template>

      <div class="orders-page__board" data-testid="orders-board">
        <button
          v-for="card in boardCards"
          :key="card.key"
          class="orders-page__board-card"
          :class="{ 'orders-page__board-card--active': card.active }"
          :data-testid="`orders-board-filter-${card.key}`"
          @click="selectBoardFilter(card.key)"
        >
          <span>{{ card.label }}</span>
          <strong>{{ card.count }}</strong>
          <em>{{ card.amountText }} · {{ card.description }}</em>
        </button>
      </div>

      <div class="orders-page__toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索订单号、用户、商品、手机号"
          clearable
          class="orders-page__search"
          data-testid="orders-search-input"
          @keyup.enter="submitSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="status" placeholder="订单状态" clearable style="width: 130px">
          <el-option
            v-for="option in ORDER_STATUS_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-button type="primary" :icon="Search" data-testid="orders-search-submit" @click="submitSearch">筛选</el-button>
        <el-button data-testid="orders-reset-filters" @click="resetFilters">重置</el-button>
        <el-button :icon="Refresh" data-testid="orders-refresh" @click="loadOrders()">刷新</el-button>
        <el-button
          type="warning"
          plain
          :loading="actionLoadingKey === 'expire-timeout-unpaid'"
          data-testid="orders-expire-timeout-unpaid"
          @click="expireTimeoutUnpaid"
        >
          扫描超时未支付
        </el-button>
      </div>

      <el-table :data="orders" v-loading="loading" stripe class="orders-page__table" data-testid="orders-table">
        <el-table-column prop="id" label="订单号" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              :type="orderStatusTagType(row.status)"
              effect="light"
              size="small"
              :data-testid="`orders-row-status-${row.id}`"
            >
              {{ orderStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="支付" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="paymentStatusTagType(row.paymentStatus)" effect="light" size="small">
              {{ paymentStatusLabel(row.paymentStatus) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="商品" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <strong :data-testid="`orders-row-title-${row.id}`">{{ row.itemTitle || "未命名商品" }}</strong>
            <span class="orders-page__muted"> 共 {{ row.itemCount }} 件</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="110" align="right">
          <template #default="{ row }">{{ formatFen(row.totalFen) }}</template>
        </el-table-column>
        <el-table-column label="收货/自提" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.receiverName || "未填写" }} {{ row.receiverPhone }}
            <span class="orders-page__muted">{{ row.deliveryAddress }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="expectTime" label="期望时间" min-width="150" show-overflow-tooltip />
        <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
        <el-table-column label="创建时间" width="170" align="center">
          <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right" align="center">
          <template #default="{ row }">
            <div class="orders-page__actions">
              <el-button link type="primary" :data-testid="`orders-open-detail-${row.id}`" @click="openDetail(row)">详情</el-button>
              <el-button
                v-for="action in ORDER_STATUS_ACTIONS[row.status]"
                :key="action.status"
                :type="action.type"
                :loading="actionLoadingKey === `${row.id}:${action.status}`"
                plain
                size="small"
                :data-testid="`orders-update-status-${row.id}-${action.status}`"
                @click="updateStatus(row, action.status)"
              >
                {{ action.label }}
              </el-button>
              <el-button
                v-if="row.paymentStatus === 'unpaid' && row.status !== 'cancelled'"
                type="warning"
                plain
                size="small"
                :loading="actionLoadingKey === `${row.id}:expire-unpaid`"
                :data-testid="`orders-expire-unpaid-${row.id}`"
                @click="expireUnpaid(row)"
              >
                关闭未支付
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="orders-page__pagination">
        <span>共 {{ total }} 单</span>
        <el-pagination
          background
          layout="prev, pager, next"
          :current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          @current-change="loadOrders"
        />
      </div>
    </el-card>

    <el-drawer
      v-model="detailVisible"
      title="订单详情"
      size="420px"
      append-to-body
      class="orders-page__drawer"
      data-testid="orders-detail-drawer"
    >
      <template v-if="selectedOrder">
        <div class="orders-page__detail">
          <div class="orders-page__detail-head">
            <strong>{{ selectedOrder.id }}</strong>
            <el-tag
              :type="orderStatusTagType(selectedOrder.status)"
              effect="light"
              :data-testid="`orders-detail-status-${selectedOrder.id}`"
            >
              {{ orderStatusLabel(selectedOrder.status) }}
            </el-tag>
          </div>

          <div class="orders-page__detail-section">
            <span class="orders-page__detail-title">商品</span>
            <div v-for="item in selectedOrder.items" :key="item.product_id" class="orders-page__item">
              <span>{{ item.title || item.product_id }}</span>
              <span>x {{ item.quantity }}</span>
              <strong>{{ formatFen(item.price_fen * item.quantity) }}</strong>
            </div>
          </div>

          <div class="orders-page__detail-section">
            <span class="orders-page__detail-title">履约信息</span>
            <p>{{ selectedOrder.receiverName || "未填写" }} {{ selectedOrder.receiverPhone }}</p>
            <p>{{ selectedOrder.deliveryType === "delivery" ? "配送" : "自提" }}</p>
            <p v-if="selectedOrder.deliveryAddress">{{ selectedOrder.deliveryAddress }}</p>
            <p>{{ selectedOrder.expectTime || "时间待确认" }}</p>
            <p v-if="selectedOrder.remark">备注：{{ selectedOrder.remark }}</p>
          </div>

          <div class="orders-page__detail-section">
            <span class="orders-page__detail-title">支付信息</span>
            <p>
              支付状态：<el-tag :type="paymentStatusTagType(selectedOrder.paymentStatus)" effect="light" size="small">
                {{ paymentStatusLabel(selectedOrder.paymentStatus) }}
              </el-tag>
            </p>
            <p>支付方式：{{ selectedOrder.paymentMethod || "未记录" }}</p>
            <p v-if="selectedOrder.paymentPaidAt">支付时间：{{ selectedOrder.paymentPaidAt }}</p>
            <p v-if="selectedOrder.paymentExpiredAt">关闭时间：{{ selectedOrder.paymentExpiredAt }}</p>
            <p v-if="selectedOrder.paymentExpiredReason">关闭原因：{{ selectedOrder.paymentExpiredReason }}</p>
          </div>

          <div class="orders-page__detail-section">
            <span class="orders-page__detail-title">金额与时间</span>
            <p>订单金额：{{ formatFen(selectedOrder.totalFen) }}</p>
            <p>创建时间：{{ formatTime(selectedOrder.createdAt) }}</p>
            <p>更新时间：{{ formatTime(selectedOrder.updatedAt) }}</p>
          </div>

          <div class="orders-page__detail-section">
            <span class="orders-page__detail-title">订单时间线</span>
            <div class="orders-page__timeline">
              <div
                v-for="event in selectedOrder.timeline"
                :key="event.id"
                class="orders-page__timeline-item"
              >
                <div class="orders-page__timeline-main">
                  <el-tag size="small" effect="plain">{{ timelineLabel(event.status) }}</el-tag>
                  <strong>{{ event.note }}</strong>
                </div>
                <p>{{ formatTime(event.createdAt) }} · {{ event.operator }}</p>
              </div>
            </div>
          </div>

          <div class="orders-page__detail-actions">
            <el-button
              v-for="action in selectedOrderActions"
              :key="action.status"
              :type="action.type"
              :loading="actionLoadingKey === `${selectedOrder.id}:${action.status}`"
              :data-testid="`orders-detail-update-status-${selectedOrder.id}-${action.status}`"
              @click="updateStatus(selectedOrder, action.status)"
            >
              {{ action.label }}
            </el-button>
            <el-button
              v-if="selectedOrderCanExpireUnpaid"
              type="warning"
              plain
              :loading="actionLoadingKey === `${selectedOrder.id}:expire-unpaid`"
              :data-testid="`orders-detail-expire-unpaid-${selectedOrder.id}`"
              @click="expireUnpaid(selectedOrder)"
            >
              关闭未支付
            </el-button>
          </div>
        </div>
      </template>
    </el-drawer>
  </section>
</template>

<style scoped>
.orders-page,
.orders-page__card {
  height: 100%;
}

.orders-page__card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: calc(100% - 57px);
}

.orders-page__header,
.orders-page__toolbar,
.orders-page__pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.orders-page__title {
  display: block;
  font-size: 15px;
  font-weight: 600;
  color: var(--yx-text);
}

.orders-page__subtitle,
.orders-page__stats,
.orders-page__muted,
.orders-page__pagination {
  color: var(--yx-text-muted);
  font-size: 13px;
}

.orders-page__stats {
  display: flex;
  gap: 12px;
}

.orders-page__toolbar {
  justify-content: flex-start;
  flex-wrap: wrap;
}

.orders-page__board {
  display: grid;
  grid-template-columns: repeat(6, minmax(118px, 1fr));
  gap: 10px;
}

.orders-page__board-card {
  display: grid;
  gap: 5px;
  min-height: 88px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  color: var(--yx-text);
  background: var(--el-fill-color-blank);
  text-align: left;
  cursor: pointer;
}

.orders-page__board-card span {
  color: var(--yx-text-muted);
  font-size: 12px;
}

.orders-page__board-card strong {
  font-size: 24px;
  line-height: 1;
}

.orders-page__board-card em {
  color: var(--yx-text-muted);
  font-size: 12px;
  font-style: normal;
  line-height: 1.4;
}

.orders-page__board-card--active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.orders-page__board-card--active span,
.orders-page__board-card--active strong {
  color: var(--el-color-primary);
}

.orders-page__search {
  width: 280px;
}

.orders-page__table {
  flex: 1;
}

.orders-page__actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex-wrap: wrap;
}

.orders-page__pagination {
  flex-shrink: 0;
}

.orders-page__detail {
  display: grid;
  gap: 18px;
}

.orders-page__detail-head,
.orders-page__item,
.orders-page__detail-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.orders-page__detail-head {
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.orders-page__detail-section {
  display: grid;
  gap: 8px;
  font-size: 13px;
  color: var(--yx-text);
}

.orders-page__detail-section p {
  margin: 0;
  color: var(--yx-text-muted);
  line-height: 1.6;
}

.orders-page__detail-title {
  font-weight: 600;
  color: var(--yx-text);
}

.orders-page__item {
  padding: 10px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.orders-page__timeline {
  display: grid;
  gap: 8px;
}

.orders-page__timeline-item {
  display: grid;
  gap: 4px;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.orders-page__timeline-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.orders-page__timeline-main strong {
  color: var(--yx-text);
  font-size: 13px;
}

.orders-page__detail-actions {
  justify-content: flex-start;
  flex-wrap: wrap;
}

@media (max-width: 767px) {
  .orders-page__header,
  .orders-page__toolbar,
  .orders-page__pagination {
    align-items: stretch;
    flex-direction: column;
  }

  .orders-page__search {
    width: 100%;
  }

  .orders-page__board {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
