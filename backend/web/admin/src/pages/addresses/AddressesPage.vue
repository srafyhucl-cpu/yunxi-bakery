<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Delete, Edit, Plus, Refresh, Search, Star } from "@element-plus/icons-vue";

import { addressesService } from "@/services/addresses";
import type { AddressDetail, AddressDraft, AddressListItem } from "@/types/address";

const loading = ref(false);
const actionLoadingKey = ref("");
const keyword = ref("");
const addresses = ref<AddressListItem[]>([]);
const currentPage = ref(1);
const total = ref(0);
const pageSize = ref(30);
const selectedAddress = ref<AddressDetail | null>(null);
const detailVisible = ref(false);
const formVisible = ref(false);
const formSubmitting = ref(false);
const formMode = ref<"create" | "edit">("create");
const formDraft = ref<AddressDraft>(createEmptyDraft());

const defaultCount = computed(() => addresses.value.filter((item) => item.isDefault).length);
const formTitle = computed(() => (formMode.value === "create" ? "新增顾客地址" : "编辑顾客地址"));

function createEmptyDraft(): AddressDraft {
  return {
    userId: "",
    receiverName: "",
    receiverPhone: "",
    address: "",
    isDefault: false,
  };
}

function formatTime(value: string): string {
  return value ? value.replace("T", " ").slice(0, 19) : "未记录";
}

function auditActionLabel(action: string): string {
  const labels: Record<string, string> = {
    create: "新增",
    update: "编辑",
    set_default: "设默认",
    delete: "删除",
  };
  return labels[action] || action;
}

async function loadAddresses(page = currentPage.value): Promise<void> {
  loading.value = true;
  try {
    const payload = await addressesService.listAddresses(page, keyword.value);
    addresses.value = payload.items;
    total.value = payload.total;
    currentPage.value = payload.page;
    pageSize.value = payload.pageSize;
  } catch {
    ElMessage.error("顾客地址加载失败");
  } finally {
    loading.value = false;
  }
}

function submitSearch(): void {
  void loadAddresses(1);
}

function resetFilters(): void {
  keyword.value = "";
  void loadAddresses(1);
}

function openCreateForm(): void {
  formMode.value = "create";
  formDraft.value = createEmptyDraft();
  formVisible.value = true;
}

function openEditForm(row: AddressListItem): void {
  formMode.value = "edit";
  formDraft.value = {
    id: row.id,
    userId: row.userId,
    receiverName: row.receiverName,
    receiverPhone: row.receiverPhone,
    address: row.address,
    isDefault: row.isDefault,
  };
  formVisible.value = true;
}

async function openDetail(row: AddressListItem): Promise<void> {
  detailVisible.value = true;
  selectedAddress.value = { ...row, auditLogs: [] };
  try {
    selectedAddress.value = await addressesService.getAddress(row.id);
  } catch {
    ElMessage.error("地址详情加载失败");
  }
}

async function saveAddress(): Promise<void> {
  formSubmitting.value = true;
  try {
    const saved = await addressesService.saveAddress(formDraft.value);
    ElMessage.success(formMode.value === "create" ? "地址已新增" : "地址已保存");
    formVisible.value = false;
    await loadAddresses(formMode.value === "create" ? 1 : currentPage.value);
    if (detailVisible.value && selectedAddress.value?.id === saved.id) {
      selectedAddress.value = await addressesService.getAddress(saved.id);
    }
  } catch {
    ElMessage.error("保存地址失败，请检查用户标识、手机号和收货地址");
  } finally {
    formSubmitting.value = false;
  }
}

async function setDefault(row: AddressListItem): Promise<void> {
  const loadingKey = `${row.id}:default`;
  actionLoadingKey.value = loadingKey;
  try {
    const updated = await addressesService.setDefault(row.id);
    addresses.value = addresses.value.map((item) => ({
      ...item,
      isDefault: item.userId === updated.userId ? item.id === updated.id : item.isDefault,
      updatedAt: item.id === updated.id ? updated.updatedAt : item.updatedAt,
    }));
    if (selectedAddress.value?.id === updated.id) {
      selectedAddress.value = await addressesService.getAddress(updated.id);
    }
    ElMessage.success("默认地址已更新");
  } catch {
    ElMessage.error("设置默认地址失败");
  } finally {
    actionLoadingKey.value = "";
  }
}

async function deleteAddress(row: AddressListItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除 ${row.receiverName} 的这个地址吗？`,
      "删除地址",
      { type: "warning" },
    );
  } catch {
    return;
  }
  const loadingKey = `${row.id}:delete`;
  actionLoadingKey.value = loadingKey;
  try {
    await addressesService.deleteAddress(row.id);
    ElMessage.success("地址已删除");
    if (selectedAddress.value?.id === row.id) {
      detailVisible.value = false;
      selectedAddress.value = null;
    }
    await loadAddresses();
  } catch {
    ElMessage.error("删除地址失败");
  } finally {
    actionLoadingKey.value = "";
  }
}

onMounted(() => {
  void loadAddresses();
});
</script>

<template>
  <section class="addresses-page" data-testid="addresses-page">
    <el-card shadow="never" class="addresses-page__card">
      <template #header>
        <div class="addresses-page__header">
          <div>
            <span class="addresses-page__title">顾客地址</span>
            <span class="addresses-page__subtitle">查看小程序用户地址簿，辅助配送核对和客服处理</span>
          </div>
          <div class="addresses-page__stats">
            <span>当前页 {{ addresses.length }} 条</span>
            <span>默认地址 {{ defaultCount }} 条</span>
          </div>
        </div>
      </template>

      <div class="addresses-page__toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索用户、联系人、手机号或地址"
          clearable
          class="addresses-page__search"
          data-testid="addresses-search-input"
          @keyup.enter="submitSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" :icon="Search" data-testid="addresses-search-submit" @click="submitSearch">筛选</el-button>
        <el-button data-testid="addresses-reset-filters" @click="resetFilters">重置</el-button>
        <el-button :icon="Refresh" data-testid="addresses-refresh" @click="loadAddresses()">刷新</el-button>
        <el-button type="primary" :icon="Plus" data-testid="addresses-create" @click="openCreateForm">新增地址</el-button>
      </div>

      <el-table :data="addresses" v-loading="loading" stripe class="addresses-page__table" data-testid="addresses-table">
        <el-table-column prop="receiverName" label="联系人" min-width="110" show-overflow-tooltip />
        <el-table-column prop="receiverPhone" label="手机号" min-width="130" show-overflow-tooltip />
        <el-table-column prop="address" label="收货地址" min-width="260" show-overflow-tooltip />
        <el-table-column label="默认" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.isDefault" type="success" effect="light" size="small">默认</el-tag>
            <el-tag v-else type="info" effect="plain" size="small">普通</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="userId" label="用户标识" min-width="190" show-overflow-tooltip />
        <el-table-column label="更新时间" width="170" align="center">
          <template #default="{ row }">{{ formatTime(row.updatedAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right" align="center">
          <template #default="{ row }">
            <div class="addresses-page__actions">
              <el-button link type="primary" :data-testid="`addresses-open-detail-${row.id}`" @click="openDetail(row)">详情</el-button>
              <el-button
                type="primary"
                plain
                size="small"
                :icon="Edit"
                :data-testid="`addresses-edit-${row.id}`"
                @click="openEditForm(row)"
              >
                编辑
              </el-button>
              <el-button
                v-if="!row.isDefault"
                type="success"
                plain
                size="small"
                :icon="Star"
                :loading="actionLoadingKey === `${row.id}:default`"
                :data-testid="`addresses-set-default-${row.id}`"
                @click="setDefault(row)"
              >
                设默认
              </el-button>
              <el-button
                type="danger"
                plain
                size="small"
                :icon="Delete"
                :loading="actionLoadingKey === `${row.id}:delete`"
                :data-testid="`addresses-delete-${row.id}`"
                @click="deleteAddress(row)"
              >
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="addresses-page__pagination">
        <span>共 {{ total }} 条地址</span>
        <el-pagination
          background
          layout="prev, pager, next"
          :current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          @current-change="loadAddresses"
        />
      </div>
    </el-card>

    <el-drawer
      v-model="detailVisible"
      title="地址详情"
      size="420px"
      append-to-body
      data-testid="addresses-detail-drawer"
    >
      <template v-if="selectedAddress">
        <div class="addresses-page__detail">
          <div class="addresses-page__detail-head">
            <strong>{{ selectedAddress.receiverName }}</strong>
            <el-tag :type="selectedAddress.isDefault ? 'success' : 'info'" effect="light">
              {{ selectedAddress.isDefault ? "默认地址" : "普通地址" }}
            </el-tag>
          </div>
          <div class="addresses-page__detail-section">
            <span class="addresses-page__detail-title">联系信息</span>
            <p>{{ selectedAddress.receiverPhone }}</p>
            <p>{{ selectedAddress.address }}</p>
          </div>
          <div class="addresses-page__detail-section">
            <span class="addresses-page__detail-title">用户与时间</span>
            <p>用户标识：{{ selectedAddress.userId }}</p>
            <p>创建时间：{{ formatTime(selectedAddress.createdAt) }}</p>
            <p>更新时间：{{ formatTime(selectedAddress.updatedAt) }}</p>
          </div>
          <div class="addresses-page__detail-section" data-testid="addresses-audit-section">
            <span class="addresses-page__detail-title">最近操作</span>
            <div v-if="selectedAddress.auditLogs.length" class="addresses-page__audit-list">
              <div
                v-for="log in selectedAddress.auditLogs"
                :key="log.id"
                class="addresses-page__audit-item"
                :data-testid="`addresses-audit-log-${log.action}`"
              >
                <div class="addresses-page__audit-main">
                  <el-tag size="small" effect="plain">{{ auditActionLabel(log.action) }}</el-tag>
                  <strong>{{ log.note || auditActionLabel(log.action) }}</strong>
                </div>
                <p>{{ formatTime(log.createdAt) }} · {{ log.operator }}</p>
              </div>
            </div>
            <p v-else>暂无操作记录</p>
          </div>
          <div class="addresses-page__detail-actions">
            <el-button
              type="primary"
              plain
              :data-testid="`addresses-detail-edit-${selectedAddress.id}`"
              @click="openEditForm(selectedAddress)"
            >
              编辑地址
            </el-button>
            <el-button
              v-if="!selectedAddress.isDefault"
              type="success"
              :loading="actionLoadingKey === `${selectedAddress.id}:default`"
              @click="setDefault(selectedAddress)"
            >
              设为默认
            </el-button>
            <el-button
              type="danger"
              plain
              :loading="actionLoadingKey === `${selectedAddress.id}:delete`"
              @click="deleteAddress(selectedAddress)"
            >
              删除地址
            </el-button>
          </div>
        </div>
      </template>
    </el-drawer>

    <el-drawer
      v-model="formVisible"
      :title="formTitle"
      size="420px"
      append-to-body
      data-testid="addresses-form-drawer"
    >
      <el-form
        label-position="top"
        class="addresses-page__form"
        data-testid="addresses-form"
        @submit.prevent
      >
        <el-form-item label="用户标识" required>
          <el-input
            v-model.trim="formDraft.userId"
            :disabled="formMode === 'edit'"
            placeholder="例如 wx_openid 或 demo-user"
            data-testid="addresses-form-user-id"
          />
        </el-form-item>
        <el-form-item label="联系人" required>
          <el-input
            v-model.trim="formDraft.receiverName"
            placeholder="收货人姓名"
            data-testid="addresses-form-receiver-name"
          />
        </el-form-item>
        <el-form-item label="手机号" required>
          <el-input
            v-model.trim="formDraft.receiverPhone"
            placeholder="11 位手机号"
            maxlength="11"
            data-testid="addresses-form-receiver-phone"
          />
        </el-form-item>
        <el-form-item label="收货地址" required>
          <el-input
            v-model.trim="formDraft.address"
            type="textarea"
            :rows="4"
            placeholder="省市区、街道、小区、门牌号"
            data-testid="addresses-form-address"
          />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="formDraft.isDefault" data-testid="addresses-form-default">设为默认地址</el-checkbox>
        </el-form-item>
        <div class="addresses-page__form-actions">
          <el-button data-testid="addresses-form-cancel" @click="formVisible = false">取消</el-button>
          <el-button
            type="primary"
            :loading="formSubmitting"
            data-testid="addresses-form-submit"
            @click="saveAddress"
          >
            保存地址
          </el-button>
        </div>
      </el-form>
    </el-drawer>
  </section>
</template>

<style scoped>
.addresses-page,
.addresses-page__card {
  height: 100%;
}

.addresses-page__card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: calc(100% - 57px);
}

.addresses-page__header,
.addresses-page__toolbar,
.addresses-page__pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.addresses-page__title {
  display: block;
  color: var(--yx-text);
  font-size: 15px;
  font-weight: 600;
}

.addresses-page__subtitle,
.addresses-page__stats,
.addresses-page__pagination {
  color: var(--yx-text-muted);
  font-size: 13px;
}

.addresses-page__stats {
  display: flex;
  gap: 12px;
}

.addresses-page__toolbar {
  justify-content: flex-start;
  flex-wrap: wrap;
}

.addresses-page__search {
  width: 320px;
}

.addresses-page__table {
  flex: 1;
}

.addresses-page__actions,
.addresses-page__detail-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: center;
}

.addresses-page__pagination {
  flex-shrink: 0;
}

.addresses-page__detail {
  display: grid;
  gap: 18px;
}

.addresses-page__form {
  display: grid;
  gap: 2px;
}

.addresses-page__detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.addresses-page__detail-section {
  display: grid;
  gap: 8px;
  color: var(--yx-text);
  font-size: 13px;
}

.addresses-page__detail-section p {
  margin: 0;
  color: var(--yx-text-muted);
  line-height: 1.6;
}

.addresses-page__detail-title {
  color: var(--yx-text);
  font-weight: 600;
}

.addresses-page__detail-actions {
  justify-content: flex-start;
}

.addresses-page__audit-list {
  display: grid;
  gap: 8px;
}

.addresses-page__audit-item {
  display: grid;
  gap: 4px;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.addresses-page__audit-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.addresses-page__audit-main strong {
  color: var(--yx-text);
  font-size: 13px;
}

.addresses-page__form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 8px;
}

@media (max-width: 767px) {
  .addresses-page__header,
  .addresses-page__toolbar,
  .addresses-page__pagination {
    align-items: stretch;
    flex-direction: column;
  }

  .addresses-page__search {
    width: 100%;
  }
}
</style>
